# 指定要编译生成的驱动模块名称
obj-m += stepper_driver.o

# 【核心配置】这里需要指向你在 WSL 中下载的树莓派内核源码路径
# 我们先预留一个常见的路径格式，后续交叉编译时如果路径不同再微调
KDIR := /home/$(USER)/linux-raspberrypi

PWD := $(shell pwd)

all:
	# 执行交叉编译，指定架构为 arm64 (对应树莓派4B的64位系统)
	make -C $(KDIR) M=$(PWD) ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- modules

clean:
	make -C $(KDIR) M=$(PWD) clean