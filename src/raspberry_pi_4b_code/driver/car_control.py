import serial
import serial.tools.list_ports  # 导入寻找端口的工具
import time
import sys
import tty
import termios

# --- 1. 自动寻找 Arduino 串口 ---
def find_arduino():
    print("正在寻找 Arduino...")
    ports = serial.tools.list_ports.comports()
    for p in ports:
        if "ACM" in p.device or "USB" in p.device:
            return p.device
    return None

SERIAL_PORT = find_arduino()

if SERIAL_PORT is None:
    print("❌ 找不到 Arduino！请检查 USB 线是否插好。")
    sys.exit()

BAUD_RATE = 115200

try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    time.sleep(2) # 等待 Arduino 重启
    print(f"✅ 成功连接到底盘，当前端口: {SERIAL_PORT}")
except Exception as e:
    print(f"❌ 串口连接失败: {e}")
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
=== 小车驾驶舱已启动 ===
  W: 前进    S: 后退
  A: 左转    D: 右转
  Space: 停止  Q: 退出
========================
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
    if ser.is_open:
        ser.close()
    print("\n串口已安全关闭。")