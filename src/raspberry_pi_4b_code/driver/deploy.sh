
#!/bin/bash



PI_USER="ray"

PI_IP="192.168.5.16" 

TARGET_DIR="/home/ray/camera_web"



echo "🚀 正在从本地 Repo 同步代码到树莓派..."

ssh ${PI_USER}@${PI_IP} "mkdir -p ${TARGET_DIR}"

scp app.py ${PI_USER}@${PI_IP}:${TARGET_DIR}/



echo "🔥 代码同步完成！正在启动图传服务..."

# 使用 libcamerify 兼容较新的树莓派系统底层驱动

ssh -t ${PI_USER}@${PI_IP} "libcamerify python3 ${TARGET_DIR}/app.py"

