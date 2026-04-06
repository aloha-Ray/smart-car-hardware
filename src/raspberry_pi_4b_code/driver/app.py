import cv2
from flask import Flask, Response, request, render_template_string
import serial
import serial.tools.list_ports
import time
import sys
import threading
import subprocess

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
# 2. 核心：独立底盘控制线程
# ==========================================
car_state = 'stop'

def chassis_control_loop():
    global car_state
    last_state = None
    
    while True:
        current = car_state
        if current != last_state:
            print(f"🚗 网页指令更新: {current}")
            
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

control_thread = threading.Thread(target=chassis_control_loop, daemon=True)
control_thread.start()

# ==========================================
# 3. 优化版：全局读图与 FFmpeg 斗鱼推流
# ==========================================
latest_frame = None

# 已填入你的斗鱼推流地址
RTMP_URL = "rtmp://sendhw3a.douyu.com/live/12827428rqZYeFQa?dyPRI=0&noforward=1&origin=hw&record=flv&roirecognition=0&stemp_id=12898962&tw=0&wm=0&wsSecret=ab56d3e28af0556cfd59a780538c07f1&wsSeek=off&wsTime=69d340fb" 

def camera_and_push_loop():
    global latest_frame
    camera = cv2.VideoCapture(0, cv2.CAP_V4L2)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    camera.set(cv2.CAP_PROP_FPS, 15) # 降低到15帧，释放CPU算力保证控制不卡顿

    pipe = None
    if RTMP_URL:
        command = [
            'ffmpeg', '-y', '-f', 'rawvideo', '-vcodec', 'rawvideo',
            '-pix_fmt', 'bgr24', '-s', '640x480', '-r', '15',
            '-i', '-', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
            '-preset', 'ultrafast', '-f', 'flv', RTMP_URL
        ]
        print("🚀 正在启动斗鱼直播推流...")
        try:
            pipe = subprocess.Popen(command, stdin=subprocess.PIPE)
        except Exception as e:
            print(f"推流组件启动失败: {e}")

    while True:
        success, frame = camera.read()
        if success:
            latest_frame = frame
            if pipe:
                try:
                    pipe.stdin.write(frame.tobytes())
                except Exception as e:
                    pass
        time.sleep(0.02)

threading.Thread(target=camera_and_push_loop, daemon=True).start()

def generate_frames():
    global latest_frame
    while True:
        if latest_frame is not None:
            ret, buffer = cv2.imencode('.jpg', latest_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        time.sleep(0.05)

# ==========================================
# 4. 前端 Web 页面
# ==========================================
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>智能小车 Web 控制台</title>
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
    <style>
        body { background: #222; color: white; text-align: center; font-family: sans-serif; margin: 0; padding: 20px; }
        .video-container { margin-bottom: 20px; }
        img { border: 3px solid #555; border-radius: 8px; width: 100%; max-width: 640px; }
        .controls { display: grid; grid-template-columns: repeat(3, 90px); gap: 10px; justify-content: center; margin-top: 20px;}
        .btn { background-color: #4CAF50; border: none; color: white; padding: 15px 0; font-size: 16px; font-weight: bold; border-radius: 10px; cursor: pointer; user-select: none; -webkit-user-select: none; touch-action: none; }
        .btn:active { background-color: #3e8e41; }
        .btn-pivot { background-color: #f39c12; }
        .btn-pivot:active { background-color: #e67e22; }
        .btn-stop { background-color: #d9534f; }
        .empty { visibility: hidden; }
    </style>
</head>
<body>
    <h2>🏎️ 树莓派斗鱼云直播车</h2>
    <div class="video-container"><img src="/video_feed"></div>
    <div class="controls">
        <button class="btn btn-pivot" onmousedown="sendCommand('q')" onmouseup="sendCommand('stop')" ontouchstart="sendCommand('q')" ontouchend="sendCommand('stop')" oncontextmenu="return false;">左掉头</button>
        <button class="btn" onmousedown="sendCommand('w')" onmouseup="sendCommand('stop')" ontouchstart="sendCommand('w')" ontouchend="sendCommand('stop')" oncontextmenu="return false;">前进</button>
        <button class="btn btn-pivot" onmousedown="sendCommand('e')" onmouseup="sendCommand('stop')" ontouchstart="sendCommand('e')" ontouchend="sendCommand('stop')" oncontextmenu="return false;">右掉头</button>
        
        <button class="btn" onmousedown="sendCommand('a')" onmouseup="sendCommand('stop')" ontouchstart="sendCommand('a')" ontouchend="sendCommand('stop')" oncontextmenu="return false;">左转</button>
        <button class="btn btn-stop" onmousedown="sendCommand('stop')" ontouchstart="sendCommand('stop')" oncontextmenu="return false;">紧急刹车</button>
        <button class="btn" onmousedown="sendCommand('d')" onmouseup="sendCommand('stop')" ontouchstart="sendCommand('d')" ontouchend="sendCommand('stop')" oncontextmenu="return false;">右转</button>
        
        <div class="empty"></div>
        <button class="btn" onmousedown="sendCommand('s')" onmouseup="sendCommand('stop')" ontouchstart="sendCommand('s')" ontouchend="sendCommand('stop')" oncontextmenu="return false;">后退</button>
        <div class="empty"></div>
    </div>
    <script>
        function sendCommand(action) {
            fetch('/action?cmd=' + action)
                .catch(error => console.error('发送失败:', error));
        }
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/action')
def handle_action():
    global car_state
    cmd = request.args.get('cmd')
    if cmd in ['w', 'a', 's', 'd', 'q', 'e', 'stop']:
        car_state = cmd
    return "OK", 200

if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)
    finally:
        car_state = 'stop'
        time.sleep(0.2)
        if ser and ser.is_open:
            ser.close()
            print("串口已安全关闭。")