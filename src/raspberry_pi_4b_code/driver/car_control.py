import serial
import time
import sys
import tty
import termios

# --- 1. 配置串口 ---
# 请确保 Arduino 插在树莓派上，设备名通常是 /dev/ttyACM0
SERIAL_PORT = '/dev/ttyACM0' 
BAUD_RATE = 115200

try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    time.sleep(2) # 等待 Arduino 重启
    print(f"成功连接到 Arduino: {SERIAL_PORT}")
except:
    print("无法连接串口，请检查 USB 线或端口名！")
    sys.exit()

# --- 2. 控制逻辑 ---
SPEED = 800  # 设定标准速度

def send_cmd(fl, rl, fr, rr):
    """格式化并发送指令"""
    command = f"{fl},{rl},{fr},{rr}\n"
    ser.write(command.encode('utf-8'))

def getch():
    """实时读取键盘按键（无需按回车）"""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(sys.stdin.fileno())
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch

# --- 3. 运行循环 ---
print("""
控制说明:
  W: 前进    S: 后退
  A: 左转    D: 右转
  Space: 停止  Q: 退出
---------------------------
""")

try:
    while True:
        key = getch().lower()
        
        if key == 'w':
            print("↑ 前进")
            send_cmd(SPEED, SPEED, SPEED, SPEED)
        elif key == 's':
            print("↓ 后退")
            send_cmd(-SPEED, -SPEED, -SPEED, -SPEED)
        elif key == 'a':
            print("← 左转 (原地)")
            send_cmd(-SPEED, -SPEED, SPEED, SPEED)
        elif key == 'd':
            print("→ 右转 (原地)")
            send_cmd(SPEED, SPEED, -SPEED, -SPEED)
        elif key == ' ':
            print("█ 停止")
            send_cmd(0, 0, 0, 0)
        elif key == 'q':
            print("退出程序")
            send_cmd(0, 0, 0, 0)
            break
            
except KeyboardInterrupt:
    send_cmd(0, 0, 0, 0)
finally:
    ser.close()
