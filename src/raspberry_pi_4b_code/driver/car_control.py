import serial
import serial.tools.list_ports
import time
import sys
import tty
import termios

# ==========================================
# 1. 自动寻找 Arduino 串口
# ==========================================
def find_arduino():
    print("正在寻找 Arduino 的大脑...")
    ports = serial.tools.list_ports.comports()
    for p in ports:
        # 匹配常见的 Arduino 串口名称
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
    time.sleep(2) # 等待 Arduino 重启就绪
    print(f"✅ 成功连接到底盘，当前端口: {SERIAL_PORT}")
except Exception as e:
    print(f"❌ 串口连接失败: {e}")
    sys.exit()

# ==========================================
# 2. 控制逻辑与基础参数
# ==========================================
SPEED = 800  # 设定标准速度

def send_cmd(fl, rl, fr, rr):
    """格式化并发送 4 个轮子的速度指令给 Arduino"""
    command = f"{fl},{rl},{fr},{rr}\n"
    ser.write(command.encode('utf-8'))

def getch():
    """实时读取键盘按键（阻塞式读取，无需按回车）"""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(sys.stdin.fileno())
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch

# ==========================================
# 3. 运行主循环 (驾驶舱)
# ==========================================
print("""
=== 🏎️ 树莓派四驱小车驾驶舱已启动 ===
  【日常行驶】(长按行驶，松开1秒后自动急刹)
    W: 直线前进    S: 直线后退
    A: 丝滑左转    D: 丝滑右转
  
  【极限机动】(木地板上阻力较大，会伴随震动声)
    Q: 原地左掉头  E: 原地右掉头
  
  【安全控制】
    Space (空格): 紧急手动刹车
    X: 安全退出程序
========================================
""")

try:
    while True:
        key = getch().lower()
        
        # 设定差速转弯时的慢速比例 (0.3 代表内侧轮子只出 30% 的力气)
        SLOW_SPEED = int(SPEED * 0.5) 

        if key == 'w':
            print("↑ 直线前进")
            send_cmd(SPEED, SPEED, SPEED, SPEED)
            
        elif key == 's':
            print("↓ 直线后退")
            send_cmd(-SPEED, -SPEED, -SPEED, -SPEED)
            
        elif key == 'a':
            print("↖ 丝滑左转 (左轮慢，右轮快)")
            send_cmd(SLOW_SPEED, SLOW_SPEED, SPEED, SPEED)
            
        elif key == 'd':
            print("↗ 丝滑右转 (左轮快，右轮慢)")
            send_cmd(SPEED, SPEED, SLOW_SPEED, SLOW_SPEED)
            
        elif key == 'q':
            print("🔄 原地左死角掉头")
            send_cmd(-SPEED, -SPEED, SPEED, SPEED)
            
        elif key == 'e':
            print("🔄 原地右死角掉头")
            send_cmd(SPEED, SPEED, -SPEED, -SPEED)
            
        elif key == ' ':
            print("█ 紧急手动刹车")
            send_cmd(0, 0, 0, 0)
            
        elif key == 'x': 
            print("退出程序...")
            send_cmd(0, 0, 0, 0)
            break
            
except KeyboardInterrupt:
    # 防止按 Ctrl+C 强制退出时小车失控
    send_cmd(0, 0, 0, 0)
finally:
    if ser.is_open:
        ser.close()
    print("\n✅ 串口已安全关闭，系统离线。")