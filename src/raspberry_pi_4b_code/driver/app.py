import cv2
from flask import Flask, Response, request, render_template_string
import serial
import serial.tools.list_ports
import time
import sys

app = Flask(__name__)

# ==========================================
# 1. 初始化底盘通信
# ==========================================
def find_arduino():
    print("🔍 正在扫描所有可用串口...")
    ports = serial.tools.list_ports.comports()
    
    if len(ports) == 0:
        print("⚠️ 树莓派没有检测到任何 USB 串口设备！")
        return None
        
    for p in ports:
        # 把所有找到的设备名称和描述都打印出来！
        print(f"👉 发现设备: {p.device} | 描述: {p.description}")
        
        # 放宽匹配条件，只要名字里带 ttyACM 或 ttyUSB 甚至 ttyAMA 都抓取
        if "ACM" in p.device or "USB" in p.device or "AMA" in p.device:
            print(f"🎯 自动锁定目标端口: {p.device}")
            return p.device
            
    # 如果还是没匹配上，强制返回列表里的第一个设备死马当活马医
    print(f"⚠️ 没匹配到标准名字，强制尝试连接: {ports[0].device}")
    return ports[0].device
SERIAL_PORT = find_arduino()
BAUD_RATE = 115200
ser = None

if SERIAL_PORT is None:
    print("❌ 找不到 Arduino！将以纯图传/测试模式启动。")
else:
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        time.sleep(2) # 等待 Arduino 重启就绪
        print(f"✅ 成功连接到底盘，当前端口: {SERIAL_PORT}")
    except Exception as e:
        print(f"❌ 串口连接失败: {e}")

# 设定标准速度和差速转弯的慢速比例
SPEED = 800
SLOW_SPEED = int(SPEED * 0.5)

def send_cmd(fl, rl, fr, rr):
    """格式化并发送 4 个轮子的速度指令给 Arduino"""
    command = f"{fl},{rl},{fr},{rr}\n"
    print(f"执行指令: {command.strip()}")
    if ser and ser.is_open:
        ser.write(command.encode('utf-8'))

# ==========================================
# 2. 初始化摄像头
# ==========================================
camera = cv2.VideoCapture(0, cv2.CAP_V4L2)
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

def generate_frames():
    while True:
        success, frame = camera.read()
        if not success:
            break
        else:
            ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

# ==========================================
# 3. 前端 Web 页面布局 (集成控制按钮)
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
        
        /* 虚拟方向盘样式 */
        .controls { display: grid; grid-template-columns: repeat(3, 90px); gap: 10px; justify-content: center; margin-top: 20px;}
        .btn { 
            background-color: #4CAF50; border: none; color: white; padding: 15px 0; 
            font-size: 16px; font-weight: bold; border-radius: 10px; cursor: pointer;
            user-select: none; -webkit-user-select: none; touch-action: manipulation;
        }
        .btn:active { background-color: #3e8e41; }
        .btn-pivot { background-color: #f39c12; }
        .btn-pivot:active { background-color: #e67e22; }
        .btn-stop { background-color: #d9534f; }
        .empty { visibility: hidden; }
    </style>
</head>
<body>
    <h2>🏎️ 树莓派四驱小车控制台</h2>
    
    <div class="video-container">
        <img src="/video_feed">
    </div>

    <!-- 结合你之前代码逻辑的控制面板 -->
    <div class="controls">
        <button class="btn btn-pivot" onmousedown="sendCommand('q')" onmouseup="sendCommand('space')" ontouchstart="sendCommand('q')" ontouchend="sendCommand('space')">原地左掉头</button>
        <button class="btn" onmousedown="sendCommand('w')" onmouseup="sendCommand('space')" ontouchstart="sendCommand('w')" ontouchend="sendCommand('space')">前进</button>
        <button class="btn btn-pivot" onmousedown="sendCommand('e')" onmouseup="sendCommand('space')" ontouchstart="sendCommand('e')" ontouchend="sendCommand('space')">原地右掉头</button>
        
        <button class="btn" onmousedown="sendCommand('a')" onmouseup="sendCommand('space')" ontouchstart="sendCommand('a')" ontouchend="sendCommand('space')">左转</button>
        <button class="btn btn-stop" onmousedown="sendCommand('space')" ontouchstart="sendCommand('space')">紧急刹车</button>
        <button class="btn" onmousedown="sendCommand('d')" onmouseup="sendCommand('space')" ontouchstart="sendCommand('d')" ontouchend="sendCommand('space')">右转</button>
        
        <div class="empty"></div>
        <button class="btn" onmousedown="sendCommand('s')" onmouseup="sendCommand('space')" ontouchstart="sendCommand('s')" ontouchend="sendCommand('space')">后退</button>
        <div class="empty"></div>
    </div>

    <script>
        let moveInterval = null; // 用于存储连续发射指令的定时器

        function sendCommand(action) {
            // 无论按下了什么，先清除上一次的“连发”定时器
            clearInterval(moveInterval);
            
            if (action === 'space') {
                // 如果是松手触发了刹车，直接发一条停止指令即可
                fetch('/action?cmd=space').catch(e => console.error(e));
            } else {
                // 如果按下了移动键，先立刻发一条指令保证极速响应
                fetch('/action?cmd=' + action).catch(e => console.error(e));
                
                // 然后开启“模拟键盘按压”模式：只要不松手，每隔 200 毫秒就发送一次
                // 这能完美喂饱 Arduino 里的 1000 毫秒看门狗！
                moveInterval = setInterval(() => {
                    fetch('/action?cmd=' + action).catch(e => console.error(e));
                }, 200);
            }
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

# ==========================================
# 4. 接收控制指令的后端 API
# ==========================================
@app.route('/action')
def handle_action():
    cmd = request.args.get('cmd')
    
    if cmd == 'w':
        print("↑ 直线前进")
        send_cmd(SPEED, SPEED, SPEED, SPEED)
    elif cmd == 's':
        print("↓ 直线后退")
        send_cmd(-SPEED, -SPEED, -SPEED, -SPEED)
    elif cmd == 'a':
        print("↖ 丝滑左转 (左轮慢，右轮快)")
        send_cmd(SLOW_SPEED, SLOW_SPEED, SPEED, SPEED)
    elif cmd == 'd':
        print("↗ 丝滑右转 (左轮快，右轮慢)")
        send_cmd(SPEED, SPEED, SLOW_SPEED, SLOW_SPEED)
    elif cmd == 'q':
        print("🔄 原地左死角掉头")
        send_cmd(-SPEED, -SPEED, SPEED, SPEED)
    elif cmd == 'e':
        print("🔄 原地右死角掉头")
        send_cmd(SPEED, SPEED, -SPEED, -SPEED)
    elif cmd == 'space':
        print("█ 手动刹车/松开按键")
        send_cmd(0, 0, 0, 0)
        
    return "OK", 200

if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=5000, threaded=True)
    finally:
        if ser and ser.is_open:
            send_cmd(0, 0, 0, 0) # 关闭服务前强制停车
            ser.close()
            print("串口已安全关闭。")