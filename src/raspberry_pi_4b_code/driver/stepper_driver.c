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