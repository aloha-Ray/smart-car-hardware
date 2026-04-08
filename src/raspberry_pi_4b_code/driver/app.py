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

# 🚀 速度调优：如果觉得追得慢，可以把 800 改为 1000-1200
SPEED = 900 
SLOW_SPEED = int(SPEED * 0.4) # 降低内侧轮转速，使转向更平滑

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
        time.sleep(0.05) # 提高底盘指令响应频率

threading.Thread(target=chassis_control_loop, daemon=True).start()

# ==========================================
# 3. 摄像头抓取线程 (针对 CSI 优化)
# ==========================================
latest_frame = None
RTMP_URL = "" 

def camera_and_push_loop():
    global latest_frame
    camera = cv2.VideoCapture(0, cv2.CAP_V4L2)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    camera.set(cv2.CAP_PROP_FPS, 20) # 尝试提升采集帧率

    while True:
        try:
            success, frame = camera.read()
            if success and frame is not None:
                latest_frame = frame
        except Exception:
            pass 
        time.sleep(0.01)

threading.Thread(target=camera_and_push_loop, daemon=True).start()

# ==========================================
# 4. 🧠 终极灵敏版 YOLO AI 跟随线程
# ==========================================
auto_follow_mode = False

def ai_tracking_loop():
    global latest_frame, car_state, auto_follow_mode
    
    path_local = os.path.join(os.path.dirname(__file__), 'yolov8n.pt')
    path_safe = '/home/ray/yolov8n.pt'
    model_path = path_local if os.path.exists(path_local) else path_safe
    
    print(f"⏳ 正在尝试加载模型: {model_path}")
    try:
        model = YOLO(model_path) 
        print("✅ YOLO AI 模型加载完毕！视觉大脑已上线！")
    except Exception as e:
        print(f"❌ 严重错误：YOLO 加载失败: {e}")
        return

    while True:
        # 如果没开启 AI 或没画面，减少 CPU 占用
        if not auto_follow_mode or latest_frame is None:
            time.sleep(0.1)
            continue

        try:
            # 🚀 优化：使用 imgsz=160 极大提速，只识别 Person (class 0)
            results = model.predict(latest_frame, classes=[0], imgsz=160, verbose=False)
            
            boxes = results[0].boxes
            if len(boxes) > 0:
                # 寻找画面中面积最大的人
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

                # 🚀 激进控制逻辑调优
                if cx < 640 * 0.42:     # 转向触发点更灵敏
                    car_state = 'a'
                elif cx > 640 * 0.58:   
                    car_state = 'd'
                else:
                    # 距离判断：离得稍远(area_ratio小)就追，离得近就停或撤
                    if area_ratio < 0.25:   # 只要你稍微退后一点，它就追
                        car_state = 'w'
                    elif area_ratio > 0.55: # 你冲向它，它会后退
                        car_state = 's'
                    else:
                        car_state = 'stop'
            else:
                car_state = 'stop' 
        except Exception:
            pass
        
        # 🚀 决策频率调优：极短休眠，让判断几乎不间断
        time.sleep(0.01) 

threading.Thread(target=ai_tracking_loop, daemon=True).start()

# ==========================================
# 5. Flask Web Server
# ==========================================
def generate_frames():
    global latest_frame
    while True:
        if latest_frame is not None:
            # 网页预览图传质量稍微降低，给 AI 腾出带宽
            ret, buffer = cv2.imencode('.jpg', latest_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
            yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        time.sleep(0.06)

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>AI 智能战车调优版</title>
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <style>
        body { background: #1a1a1a; color: white; text-align: center; font-family: sans-serif; margin: 0; padding: 20px; }
        img { border: 3px solid #9b59b6; border-radius: 8px; width: 100%; max-width: 600px; }
        .controls { display: grid; grid-template-columns: repeat(3, 90px); gap: 10px; justify-content: center; margin-top: 20px;}
        .btn { background-color: #444; border: none; color: white; padding: 15px 0; font-size: 16px; font-weight: bold; border-radius: 10px; touch-action: none; cursor: pointer;}
        .btn:active { background-color: #666; }
        .btn-ai { background-color: #9b59b6; grid-column: span 3; font-size: 18px; margin-top: 10px; animation: pulse 2s infinite; }
        @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.8; } 100% { opacity: 1; } }
    </style>
</head>
<body>
    <h2 style="color: #9b59b6;">⚡ 极速跟随模式 ⚡</h2>
    <div><img src="/video_feed"></div>
    <div class="controls">
        <button class="btn" onmousedown="sendCommand('q')" onmouseup="sendCommand('stop')" ontouchstart="sendCommand('q')" ontouchend="sendCommand('stop')">左旋</button>
        <button class="btn" onmousedown="sendCommand('w')" onmouseup="sendCommand('stop')" ontouchstart="sendCommand('w')" ontouchend="sendCommand('stop')">前</button>
        <button class="btn" onmousedown="sendCommand('e')" onmouseup="sendCommand('stop')" ontouchstart="sendCommand('e')" ontouchend="sendCommand('stop')">右旋</button>
        <button class="btn" onmousedown="sendCommand('a')" onmouseup="sendCommand('stop')" ontouchstart="sendCommand('a')" ontouchend="sendCommand('stop')">左</button>
        <button class="btn" style="background:#d9534f;" onmousedown="sendCommand('stop')">停</button>
        <button class="btn" onmousedown="sendCommand('d')" onmouseup="sendCommand('stop')" ontouchstart="sendCommand('d')" ontouchend="sendCommand('stop')">右</button>
        <button class="btn" id="ai-btn" class="btn-ai" style="background:#9b59b6;grid-column: span 3;padding:20px 0;" onclick="toggleAI()">🚀 启动 视觉跟随大脑</button>
    </div>
    <script>
        let isAI = false;
        function toggleAI() {
            isAI = !isAI;
            const btn = document.getElementById('ai-btn');
            if (isAI) {
                btn.innerHTML = '🛑 停止视觉跟随'; btn.style.backgroundColor = '#e74c3c';
                fetch('/action?cmd=ai_on');
            } else {
                btn.innerHTML = '🚀 启动 视觉跟随大脑'; btn.style.backgroundColor = '#9b59b6';
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
    # threaded=True 开启多线程模式提高并发
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)