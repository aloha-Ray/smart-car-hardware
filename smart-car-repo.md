# smart-car-repo

### 一、前期硬件选型

<img src="images/物料.png" width="80%">

### 二、系统框图

<img src="images/系统框图.png" width="80%">

### 三、系统搭建以及测试

#### 3.1组装42电机以及轮子

!<img src="images/小车底盘.jpg" width="80%">

#### 3.2组装上层驱动

将TMC2209固定至CNC shield V3，并将42步进电机与TMC2209电机驱动模块相连

<img src="images/上层驱动.jpg" width="80%">

连接电池测试驱动模块，用万用表测量TMC2209模块的VREF，使用螺丝刀扭动螺丝，使VREF的值保持在0.9V左右，并小心静电击穿。

<img src="images/测量电压.jpg" width="80%">

测试完毕后，使用铜柱将开发板固定好

#### 3.4编写树莓派linux内核驱动代码测试

打开 `src/raspberry_pi_4b_code/driver/` 文件夹

编写 C 语言驱动源码 (`stepper_driver.c`)

~~~c
#include <linux/module.h>
#include <linux/init.h>
#include <linux/gpio.h>
#include <linux/fs.h>
#include <linux/uaccess.h>

// 给驱动起名字
#define DRIVER_NAME "stepper_gpio_driver"
// 设定要控制的树莓派引脚
#define STEP_PIN 17 

static int major_number; // 用于保存系统分配给这个驱动的主设备号
static ssize_t dev_write(struct file *filep, const char *buffer, size_t len, loff_t *offset) {
    char cmd;
    
    // 把传进来的指令安全地拷贝到内核里
    if (copy_from_user(&cmd, buffer, 1)) {
        return -EFAULT;
    }

    // 根据指令控制引脚的电压S
    if (cmd == '1') {
        gpio_set_value(STEP_PIN, 1); // 输出高电平
    } else if (cmd == '0') {
        gpio_set_value(STEP_PIN, 0); // 输出低电平
    }
    return len;
}

static struct file_operations fops = {
    .write = dev_write,
};

static int __init stepper_driver_init(void) {
    printk(KERN_INFO "Stepper Driver: 正在启动电机驱动...\n");

    //向系统申请霸占 GPIO 17 引脚
    if (!gpio_is_valid(STEP_PIN)) {
        printk(KERN_ERR "Stepper Driver: 申请 GPIO 引脚失败！\n");
        return -ENODEV;
    }
    gpio_request(STEP_PIN, "sysfs");
    gpio_direction_output(STEP_PIN, 0); // 默认先输出低电平，防止电机乱动

    // 向系统注册这个驱动，并获取“身份证号”
    major_number = register_chrdev(0, DRIVER_NAME, &fops);
    if (major_number < 0) {
        printk(KERN_ERR "Stepper Driver: 注册失败！\n");
        gpio_free(STEP_PIN);
        return major_number;
    }
    
    printk(KERN_INFO "Stepper Driver: 注册成功！分配的主设备号是 %d\n", major_number);
    return 0;
}

static void __exit stepper_driver_exit(void) {
    unregister_chrdev(major_number, DRIVER_NAME); // 注销身份证号
    gpio_set_value(STEP_PIN, 0);                  // 安全起见，电压拉低
    gpio_free(STEP_PIN);                          // 把引脚还给系统
    printk(KERN_INFO "Stepper Driver: 驱动已安全卸载。\n");
}

// 标记入口和出口函数
module_init(stepper_driver_init);
module_exit(stepper_driver_exit);

// 必须声明开源许可证，否则 Linux 内核会拒绝加载
MODULE_LICENSE("GPL");
MODULE_AUTHOR("Ray");
MODULE_DESCRIPTION("树莓派步进电机高精度 GPIO 驱动");
~~~

编写编译规则 (`Makefile`)

~~~ c
# 告诉编译器我们要生成的驱动文件名叫什么
obj-m += stepper_driver.o

# 【极其重要】指向你刚刚下载好的树莓派内核源码的路径
# $(USER) 会自动获取你当前的 Linux 用户名S
KDIR := /home/ray/linux

PWD := $(shell pwd)

all:
	make -C $(KDIR) M=$(PWD) ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- modules

clean:
	make -C $(KDIR) M=$(PWD) clean
~~~

#### 3.5 把树莓派官方的**Linux 内核源码**下载到 WSL 环境里

进入linux主目录

~~~ 
cd ~
~~~

执行克隆命令开始下载

~~~
git clone --depth=1 https://github.com/raspberrypi/linux.git
~~~

下载完成，查看

进入内核源码目录

~~~
cd ~/linux
~~~

加载树莓派 4B 的默认配置

~~~
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- bcm2711_defconfig
~~~

生成一些脚本和头文件

~~~
make ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- modules_prepare
~~~

回到写底层代码的 D 盘文件夹

~~~
cd /mnt/d/car/smart-car-repo/src/raspberry_pi_4b_code/driver/
~~~

然后make

#### 3.6 把驱动传送到树莓派

~~~
cd /mnt/d/car/smart-car-repo/src/raspberry_pi_4b_code/driver/
scp stepper_driver.ko ray@192.168:~
~~~

#### 3.7 把树莓派当大脑，arduino当作小脑

编写 Arduino “小脑”固件，使用串口通信，接受树莓派的指令，然后交由arduino来处理

~~~c++
#include <linux/module.h>
#include <linux/init.h>
#include <linux/gpio.h>
#include <linux/fs.h>
#include <linux/uaccess.h>

#define DRIVER_NAME "stepper_gpio_driver"
// 假设将树莓派的 GPIO 17 引脚连接到 CNC Shield V3 对应的 STEP 引脚
#define STEP_PIN 17 

static int major_number;

// 这个函数负责接收外部传来的指令（1或0），并控制引脚电平
static ssize_t dev_write(struct file *filep, const char *buffer, size_t len, loff_t *offset) {
    char cmd;
    // 将应用层（比如你以后写的 Python 脚本）发来的指令拷贝进内核
    if (copy_from_user(&cmd, buffer, 1)) {
        return -EFAULT;
    }

    // 判断指令并操作底层硬件
    if (cmd == '1') {
        gpio_set_value(STEP_PIN, 1); // 输出高电平
    } else if (cmd == '0') {
        gpio_set_value(STEP_PIN, 0); // 输出低电平
    }
    return len;
}

// 绑定设备的文件操作接口
static struct file_operations fops = {
    .write = dev_write,
};

// 驱动加载时的初始化动作
static int __init stepper_driver_init(void) {
    printk(KERN_INFO "Stepper Driver: 正在初始化...\n");

    // 检查并申请树莓派的 GPIO 引脚
    if (!gpio_is_valid(STEP_PIN)) {
        printk(KERN_ERR "Stepper Driver: 无效的 GPIO 引脚\n");
        return -ENODEV;
    }
    gpio_request(STEP_PIN, "sysfs");
    gpio_direction_output(STEP_PIN, 0); // 初始状态设为低电平

    // 注册这个字符设备驱动
    major_number = register_chrdev(0, DRIVER_NAME, &fops);
    if (major_number < 0) {
        printk(KERN_ERR "Stepper Driver: 注册主设备号失败\n");
        gpio_free(STEP_PIN);
        return major_number;
    }
    printk(KERN_INFO "Stepper Driver: 注册成功，分配的主设备号是 %d\n", major_number);
    return 0;
}

// 驱动卸载时的清理动作
static void __exit stepper_driver_exit(void) {
    unregister_chrdev(major_number, DRIVER_NAME);
    gpio_set_value(STEP_PIN, 0); // 安全起见，卸载时拉低电平
    gpio_free(STEP_PIN);         // 释放对该引脚的控制权
    printk(KERN_INFO "Stepper Driver: 驱动已卸载。\n");
}

module_init(stepper_driver_init);
module_exit(stepper_driver_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Your Name");
MODULE_DESCRIPTION("树莓派底层步进电机 GPIO 驱动");
~~~

树莓派端

~~~python
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
~~~

小车键盘控制测试照片

<img src="images/控制测试照片.jpg" width="80%">

控制测试视频，见/video文件夹

### 四、硬件驱动搭建

#### 4.1 摄像头驱动

硬件选型：树莓派csi摄像头及摄像头支架

摄像头测试程序

~~~~c
#include <stdio.h>
#include <stdlib.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/ioctl.h>
#include <linux/videodev2.h>

int main() {
    // 尝试打开默认的摄像头设备节点
    int fd = open("/dev/video0", O_RDWR);
    if (fd == -1) {
        perror("Error: 无法打开摄像头设备 /dev/video0");
        return 1;
    }

    // 查询摄像头能力/属性
    struct v4l2_capability cap;
    if (ioctl(fd, VIDIOC_QUERYCAP, &cap) == -1) {
        perror("Error: 无法查询设备属性");
        close(fd);
        return 1;
    }

    printf("==============================\n");
    printf("成功连接 OV5647 (或默认摄像头)!\n");
    printf("驱动程序: %s\n", cap.driver);
    printf("设备名称: %s\n", cap.card);
    printf("总线信息: %s\n", cap.bus_info);
    printf("版本号: %u.%u.%u\n", 
            (cap.version >> 16) & 0xFF, 
            (cap.version >> 8) & 0xFF, 
            cap.version & 0xFF);
    printf("==============================\n");

    close(fd);
    return 0;
}
~~~~

编写 Web 图传核心代码

~~~~python
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
~~~~

在 Windows 10 的浏览器中输入 `http:192.168.x.x:5000`

<img src="images/web页面.jpg" width="80%">

具体视频看/video文件夹

#### 4.2 视频推流到斗鱼平台

~~~~python
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
~~~~

<img src="images/小车推流.jpg" width="80%">

#### 4.3 小车yolo模型自动跟踪

下载yolo模型时出现的部分问题

<img src="images/cuowu1.png" width="80%">

<img src="images/cuowu2.png" width="80%">

~~~~python
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
~~~~

