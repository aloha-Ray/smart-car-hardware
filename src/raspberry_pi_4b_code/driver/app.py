import cv2
from flask import Flask, Response, request, render_template_string
import serial
import serial.tools.list_ports
import time
import threading
import os
from ultralytics import YOLO

app = Flask(__name__)

# ==========================================
# 1. 初始化底盘通信
# ==========================================
def find_arduino():
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
        print(f"✅ 底盘连接成功: {SERIAL_PORT}")
    except Exception as e:
        print(f"❌ 串口连接失败: {e}")

# 速度配置
SPEED = 900 
SLOW_SPEED = int(SPEED * 0.4)

def send_cmd(fl, rl, fr, rr):
    command = f"{fl},{rl},{fr},{rr}\n"
    if ser and ser.is_open:
        ser.write(command.encode('utf-8'))

# ==========================================
# 2. 独立底盘控制线程 (负责物理执行)
# ==========================================
car_state = 'stop'

def chassis_control_loop():
    global car_state
    last_state = None
    while True:
        current = car_state
        if current != last_state:
            print(f"🚗 底盘状态切换为: {current}")
            
        if current == 'w': send_cmd(SPEED, SPEED, SPEED, SPEED)      # 前进
        elif current == 's': send_cmd(-SPEED, -SPEED, -SPEED, -SPEED) # 后退
        elif current == 'a': send_cmd(SLOW_SPEED, SLOW_SPEED, SPEED, SPEED) # 左转
        elif current == 'd': send_cmd(SPEED, SPEED, SLOW_SPEED, SLOW_SPEED) # 右转
        elif current == 'stop':
            if last_state != 'stop':
                send_cmd(0, 0, 0, 0) # 只有从运动变为停止时发送一次 0
                
        last_state = current
        time.sleep(0.05)

threading.Thread(target=chassis_control_loop, daemon=True).start()

# ==========================================
# 3. 摄像头抓取线程
# ==========================================
latest_frame = None

def camera_loop():
    global latest_frame
    camera = cv2.VideoCapture(0, cv2.CAP_V4L2)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    camera.set(cv2.CAP_PROP_FPS, 20)

    while True:
        try:
            success, frame = camera.read()
            if success and frame is not None:
                latest_frame = frame
        except Exception: pass 
        time.sleep(0.01)

threading.Thread(target=camera_loop, daemon=True).start()

# ==========================================
# 4. 🧠 YOLO AI 跟随线程 (修复退出遗留Bug)
# ==========================================
auto_follow_mode = False

def ai_tracking_loop():
    global latest_frame, car_state, auto_follow_mode
    
    model_path = '/home/ray/yolov8n.pt'
    try:
        model = YOLO(model_path) 
        print("✅ YOLO AI 视觉大脑已就绪！")
    except Exception as e:
        print(f"❌ 模型加载失败: {e}")
        return

    while True:
        # 💡 如果关闭了 AI 模式，确保将状态设为停止，并进入休眠
        if not auto_follow_mode:
            time.sleep(0.1)
            continue

        if latest_frame is None:
            time.sleep(0.1)
            continue

        try:
            # 极速推理
            results = model.predict(latest_frame, classes=[0], imgsz=160, verbose=False)
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

                # 核心跟随逻辑调优
                if cx < 640 * 0.42:     car_state = 'a' # 偏左
                elif cx > 640 * 0.58:   car_state = 'd' # 偏右
                else:
                    if area_ratio < 0.25:   car_state = 'w' # 远了，追
                    elif area_ratio > 0.55: car_state = 's' # 太近，撤
                    else:                   car_state = 'stop' # 恰好，停
            else:
                # 💡 画面里没人，立刻设为停止
                car_state = 'stop' 
        except Exception:
            car_state = 'stop'
            
        time.sleep(0.01) 

threading.Thread(target=ai_tracking_loop, daemon=True).start()

# ==========================================
# 5. Web 路由与控制逻辑
# ==========================================
def generate_frames():
    global latest_frame
    while True:
        if latest_frame is not None:
            ret, buffer = cv2.imencode('.jpg', latest_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
            yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        time.sleep(0.06)

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>AI 智能战车</title>
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <style>
        body { background: #1a1a1a; color: white; text-align: center; font-family: sans-serif; margin: 0; padding: 10px; }
        img { border: 3px solid #9b59b6; border-radius: 8px; width: 100%; max-width: 500px; }
        .controls { display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; max-width: 300px; margin: 20px auto; }
        .btn { background-color: #444; border: none; color: white; height: 70px; font-size: 20px; font-weight: bold; border-radius: 12px; touch-action: none; cursor: pointer; display: flex; align-items: center; justify-content: center; }
        .btn:active { background-color: #666; }
        .btn-stop { background-color: #d9534f; }
        .btn-ai { background-color: #9b59b6; grid-column: span 3; margin-top: 10px; }
        .empty { visibility: hidden; }
    </style>
</head>
<body>
    <h2 style="color: #9b59b6; margin: 5px;">🤖 AI 战车控制台</h2>
    <div><img src="/video_feed"></div>
    
    <div class="controls">
        <div class="empty"></div>
        <button class="btn" onmousedown="sendCommand('w')" onmouseup="sendCommand('stop')" ontouchstart="sendCommand('w')" ontouchend="sendCommand('stop')">前</button>
        <div class="empty"></div>
        
        <button class="btn" onmousedown="sendCommand('a')" onmouseup="sendCommand('stop')" ontouchstart="sendCommand('a')" ontouchend="sendCommand('stop')">左</button>
        <button class="btn btn-stop" onmousedown="sendCommand('stop')" ontouchstart="sendCommand('stop')">停</button>
        <button class="btn" onmousedown="sendCommand('d')" onmouseup="sendCommand('stop')" ontouchstart="sendCommand('d')" ontouchend="sendCommand('stop')">右</button>
        
        <div class="empty"></div>
        <button class="btn" onmousedown="sendCommand('s')" onmouseup="sendCommand('stop')" ontouchstart="sendCommand('s')" ontouchend="sendCommand('stop')">后</button>
        <div class="empty"></div>
        
        <button class="btn btn-ai" id="ai-btn" onclick="toggleAI()">🚀 开启视觉跟随</button>
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
                btn.innerHTML = '🚀 开启视觉跟随'; btn.style.backgroundColor = '#9b59b6';
                fetch('/action?cmd=ai_off');
            }
        }
        function sendCommand(action) {
            // 如果在AI模式下点击手动方向键，强制关闭AI
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
    
    if cmd == 'ai_on':
        auto_follow_mode = True
    elif cmd == 'ai_off':
        auto_follow_mode = False
        car_state = 'stop' # 💡 关键修复：关闭时强制将变量设为 stop
        send_cmd(0, 0, 0, 0) # 💡 关键修复：立刻发送停止信号
    elif cmd in ['w', 'a', 's', 'd', 'stop']:
        car_state = cmd
        
    return "OK", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)