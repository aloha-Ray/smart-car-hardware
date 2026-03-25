# smart-car-repo

### 一、前期硬件选型

![物料](images\物料.png)

### 二、系统框图

![1774420862974](C:\Users\86136\AppData\Roaming\Typora\typora-user-images\1774420862974.png)

### 三、系统搭建以及测试

#### 3.1组装42电机以及轮子

![1774421444986](C:\Users\86136\AppData\Roaming\Typora\typora-user-images\1774421444986.png)

#### 3.2组装上层驱动

将TMC2209固定至CNC shield V3，并将42步进电机与TMC2209电机驱动模块相连

![1774421740245](C:\Users\86136\AppData\Roaming\Typora\typora-user-images\1774421740245.png)

连接电池测试驱动模块，用万用表测量TMC2209模块的VREF，使用螺丝刀扭动螺丝，使VREF的值保持在0.9V左右，并小心静电击穿。

![1774422102214](C:\Users\86136\AppData\Roaming\Typora\typora-user-images\1774422102214.png)

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

    // 根据指令控制引脚的电压
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

![1774423446978](C:\Users\86136\AppData\Roaming\Typora\typora-user-images\1774423446978.png)

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

编写 Arduino “小脑”固件

~~~c++
#include <AccelStepper.h>

// --- CNC Shield V3 引脚定义 (4独立轴) ---
#define EN_PIN 8  // 全部驱动的全局使能引脚

// 1. 左前轮 (接入 X 轴插槽)
#define FL_STEP 2
#define FL_DIR  5
// 2. 左后轮 (接入 Y 轴插槽)
#define RL_STEP 3
#define RL_DIR  6
// 3. 右前轮 (接入 Z 轴插槽)
#define FR_STEP 4
#define FR_DIR  7
// 4. 右后轮 (接入 A 轴插槽)
#define RR_STEP 12 
#define RR_DIR  13 

// --- 创建 4 个独立电机对象 ---
AccelStepper motorFL(1, FL_STEP, FL_DIR);  
AccelStepper motorRL(1, RL_STEP, RL_DIR); 
AccelStepper motorFR(1, FR_STEP, FR_DIR); 
AccelStepper motorRR(1, RR_STEP, RR_DIR); 

String inputString = "";
bool stringComplete = false;

void setup() {
  Serial.begin(115200);
  
  pinMode(EN_PIN, OUTPUT);
  digitalWrite(EN_PIN, LOW); // 激活所有电机

  // --- 统一配置 4 个电机的参数 ---
  AccelStepper* motors[] = {&motorFL, &motorRL, &motorFR, &motorRR};
  for (int i = 0; i < 4; i++) {
    motors[i]->setMaxSpeed(2000.0);    // 最大速度
    motors[i]->setAcceleration(800.0); // 加速度 (数值越小起步越柔和，TMC2209 可以适当调高)
  }
  
  Serial.println("四驱静音小脑已启动...");
  Serial.println("指令格式: 左前,左后,右前,右后 (例如: 500,500,500,500)");
}

void loop() {
  if (stringComplete) {
    parseCommand(inputString);
    inputString = "";       
    stringComplete = false; 
  }

  // 4 个轮子疯狂运转 (必须放在无阻塞的 loop 中)
  motorFL.runSpeed();
  motorRL.runSpeed();
  motorFR.runSpeed();
  motorRR.runSpeed();
}

void serialEvent() {
  while (Serial.available()) {
    char inChar = (char)Serial.read();
    if (inChar == '\n') {
      stringComplete = true;
    } else {
      inputString += inChar; 
    }
  }
}

// --- 拆解 4 个数字的指令 ---
void parseCommand(String cmd) {
  int comma1 = cmd.indexOf(',');
  int comma2 = cmd.indexOf(',', comma1 + 1);
  int comma3 = cmd.indexOf(',', comma2 + 1);

  // 确保找到了 3 个逗号，格式才算正确
  if (comma1 != -1 && comma2 != -1 && comma3 != -1) { 
    float flSpeed = cmd.substring(0, comma1).toFloat();
    float rlSpeed = cmd.substring(comma1 + 1, comma2).toFloat();
    float frSpeed = cmd.substring(comma2 + 1, comma3).toFloat();
    float rrSpeed = cmd.substring(comma3 + 1).toFloat();

    motorFL.setSpeed(flSpeed);
    motorRL.setSpeed(rlSpeed);
    motorFR.setSpeed(frSpeed);
    motorRR.setSpeed(rrSpeed);
    
    Serial.print("已执行 -> ");
    Serial.print(flSpeed); Serial.print(" | ");
    Serial.print(rlSpeed); Serial.print(" | ");
    Serial.print(frSpeed); Serial.print(" | ");
    Serial.println(rrSpeed);
  } else {
    Serial.println("错误！格式必须是四个数字: FL,RL,FR,RR");
  }
}
~~~

树莓派端

~~~python
import serial
import time

# 1. 直接打开系统自带的串口设备（极其简单！）
ser = serial.Serial('/dev/ttyACM0', 115200)
time.sleep(2) # 等待 Arduino 重启准备好

# 2. 给 Arduino 下达“全速前进”指令
print("小车前进！")
ser.write(b"500,500\n") 
time.sleep(3) # 让小车跑 3 秒

# 3. 下达“刹车”指令
print("小车停止！")
ser.write(b"0,0\n")
~~~

