import cv2
from flask import Flask, Response, request, render_template_string
import serial
import serial.tools.list_ports
import time
import threading
import subprocess
import os
from ultralytics import YOLO

app = Flask(__name__)

# ==========================================
# 1. 初始化底盘通信
# ==========================================
def find_arduino():
    print("正在寻找 Arduino 的大脑...")
    ports = serial.tools.list_ports.comports()
    for p in ports:
        if "ACM" in p.device or "USB" in p.device:
            return p.device
    return None

SERIAL_PORT = find_arduino()
BAUD_RATE = 115200
ser = None

if SERIAL_PORT:
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        time.sleep(2)
        print(f"✅ 成功连接到底盘，当前端口: {SERIAL_PORT}")
    except Exception as e:
        print(f"❌ 串口连接失败: {e}")

SPEED = 800
SLOW_SPEED = int(SPEED * 0.5)

def send_cmd(fl, rl, fr, rr):
    command = f"{fl},{rl},{fr},{rr}\n"
    if ser and ser.is_open:
        ser.write(command.encode('utf-8'))

# ==========================================
# 2. 独立底盘控制线程
# ==========================================
car_state = 'stop'

def chassis_control_loop():
    global car_state
    last_state = None
    while True:
        current = car_state
        if current != last_state:
            print(f"🚗 状态更新: {current}")
            
        if current == 'w': send_cmd(SPEED, SPEED, SPEED, SPEED)
        elif current == 's': send_cmd(-SPEED, -SPEED, -SPEED, -SPEED)
        elif current == 'a': send_cmd(SLOW_SPEED, SLOW_SPEED, SPEED, SPEED)
        elif current == 'd': send_cmd(SPEED, SPEED, SLOW_SPEED, SLOW_SPEED)
        elif current == 'q': send_cmd(-SPEED, -SPEED, SPEED, SPEED)
        elif current == 'e': send_cmd(SPEED, SPEED, -SPEED, -SPEED)
        elif current == 'stop':
            if last_state != 'stop':
                send_cmd(0, 0, 0, 0)
                
        last_state = current
        time.sleep(0.1)

threading.Thread(target=chassis_control_loop, daemon=True).start()

# ==========================================
# 3. 摄像头抓取线程 (针对 CSI 优化)
# ==========================================
latest_frame = None
RTMP_URL = "" # 如需推流到斗鱼请填入

def camera_and_push_loop():
    global latest_frame
    # 树莓派排线摄像头必须带 CAP_V4L2
    camera = cv2.VideoCapture(0, cv2.CAP_V4L2)
    
    # 💡 修复绿屏关键：仅设置宽高，不设置 FOURCC 格式
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    camera.set(cv2.CAP_PROP_FPS, 15) 

    pipe = None
    if RTMP_URL:
        command = [
            'ffmpeg', '-y', '-f', 'rawvideo', '-vcodec', 'rawvideo',
            '-pix_fmt', 'bgr24', '-s', '640x480', '-r', '15',
            '-i', '-', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
            '-preset', 'ultrafast', '-f', 'flv', RTMP_URL
        ]
        try:
            pipe = subprocess.Popen(command, stdin=subprocess.PIPE)
            print("🚀 直播推流引擎启动成功！")
        except: pass

    while True:
        try:
            success, frame = camera.read()
            if success and frame is not None:
                latest_frame = frame
                if pipe:
                    try: pipe.stdin.write(frame.tobytes())
                    except: pass
        except Exception:
            pass # 跳过坏帧
        time.sleep(0.02)

threading.Thread(target=camera_and_push_loop, daemon=True).start()

# ==========================================
# 4. 🧠 YOLO AI 跟随线程 (增强加载逻辑)
# ==========================================
auto_follow_mode = False

def ai_tracking_loop():
    global latest_frame, car_state, auto_follow_mode
    
    # 💡 尝试两个路径，确保模型能被找到
    path_local = os.path.join(os.path.dirname(__file__), 'yolov8n.pt')
    path_safe = '/home/ray/yolov8n.pt'
    
    model_path = path_local if os.path.exists(path_local) else path_safe
    
    print(f"⏳ 正在尝试加载模型: {model_path}")
    
    try:
        if not os.path.exists(model_path):
            print(f"❌ 找不到模型文件！请确保执行了 scp 传输。")
            return
        
        # 校验文件大小，防止 Ran out of input (空文件报错)
        if os.path.getsize(model_path) < 5000000:
            print(f"⚠️ 警告：{model_path} 文件太小，可能已损坏。建议重新上传！")
            return

        model = YOLO(model_path) 
        print("✅ YOLO AI 模型加载完毕！视觉大脑已上线！")
    except Exception as e:
        print(f"❌ 严重错误：YOLO 加载崩溃，原因：{e}")
        return

    while True:
        if not auto_follow_mode or latest_frame is None:
            time.sleep(0.2)
            continue

        try:
            frame = latest_frame.copy()
            results = model.predict(frame, classes=[0], imgsz=320, verbose=False)
            
            boxes = results[0].boxes
            if len(boxes) > 0:
                max_area = 0
                best_box = None
                for box in boxes:
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    area = (x2 - x1) * (y2 - y1)
                    if area > max_area:
                        max_area = area
                        best_box = [x1, y1, x2, y2]
                
                x1, y1, x2, y2 = best_box
                cx = (x1 + x2) / 2
                frame_area = 640 * 480
                area_ratio = max_area / frame_area

                if cx < 640 * 0.35:     car_state = 'a'
                elif cx > 640 * 0.65:   car_state = 'd'
                else:
                    if area_ratio < 0.15: car_state = 'w'
                    elif area_ratio > 0.40: car_state = 's'
                    else: car_state = 'stop'
            else:
                car_state = 'stop'
        except Exception:
            pass
        time.sleep(0.2) 

threading.Thread(target=ai_tracking_loop, daemon=True).start()

# ==========================================
# 5. Flask Web Server
# ==========================================
def generate_frames():
    global latest_frame
    while True:
        if latest_frame is not None:
            ret, buffer = cv2.imencode('.jpg', latest_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        time.sleep(0.05)

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>YOLO 智能战车</title>
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <style>
        body { background: #222; color: white; text-align: center; font-family: sans-serif; margin: 0; padding: 20px; }
        img { border: 3px solid #555; border-radius: 8px; width: 100%; max-width: 640px; }
        .controls { display: grid; grid-template-columns: repeat(3, 90px); gap: 10px; justify-content: center; margin-top: 20px;}
        .btn { background-color: #4CAF50; border: none; color: white; padding: 15px 0; font-size: 16px; font-weight: bold; border-radius: 10px; touch-action: none; }
        .btn-stop { background-color: #d9534f; }
        .btn-ai { background-color: #9b59b6; grid-column: span 3; font-size: 18px; margin-top: 10px;}
    </style>
</head>
<body>
    <h2>🤖 YOLO 自动跟随战车</h2>
    <div><img src="/video_feed"></div>
    <div class="controls">
        <button class="btn" onmousedown="sendCommand('q')" onmouseup="sendCommand('stop')" ontouchstart="sendCommand('q')" ontouchend="sendCommand('stop')">左掉头</button>
        <button class="btn" onmousedown="sendCommand('w')" onmouseup="sendCommand('stop')" ontouchstart="sendCommand('w')" ontouchend="sendCommand('stop')">前进</button>
        <button class="btn" onmousedown="sendCommand('e')" onmouseup="sendCommand('stop')" ontouchstart="sendCommand('e')" ontouchend="sendCommand('stop')">右掉头</button>
        <button class="btn" onmousedown="sendCommand('a')" onmouseup="sendCommand('stop')" ontouchstart="sendCommand('a')" ontouchend="sendCommand('stop')">左转</button>
        <button class="btn btn-stop" onmousedown="sendCommand('stop')" ontouchstart="sendCommand('stop')">刹车</button>
        <button class="btn" onmousedown="sendCommand('d')" onmouseup="sendCommand('stop')" ontouchstart="sendCommand('d')" ontouchend="sendCommand('stop')">右转</button>
        <button class="btn btn-ai" id="ai-btn" onclick="toggleAI()">🚀 开启 AI 跟随</button>
    </div>
    <script>
        let isAI = false;
        function toggleAI() {
            isAI = !isAI;
            const btn = document.getElementById('ai-btn');
            if (isAI) {
                btn.innerHTML = '🛑 停止自动跟随'; btn.style.backgroundColor = '#e74c3c';
                fetch('/action?cmd=ai_on');
            } else {
                btn.innerHTML = '🚀 开启 AI 跟随'; btn.style.backgroundColor = '#9b59b6';
                fetch('/action?cmd=ai_off');
            }
        }
        function sendCommand(action) {
            if (isAI && action !== 'stop') toggleAI(); 
            fetch('/action?cmd=' + action);
        }
    </script>
</body>
</html>
'''

@app.route('/')
def index(): return render_template_string(HTML_TEMPLATE)

@app.route('/video_feed')
def video_feed(): return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/action')
def handle_action():
    global car_state, auto_follow_mode
    cmd = request.args.get('cmd')
    if cmd == 'ai_on': auto_follow_mode = True
    elif cmd == 'ai_off': auto_follow_mode = False; car_state = 'stop'
    elif cmd in ['w', 'a', 's', 'd', 'q', 'e', 'stop']: car_state = cmd
    return "OK", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)