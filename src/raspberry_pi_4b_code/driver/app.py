import cv2
from flask import Flask, Response

app = Flask(__name__)

# 增加 cv2.CAP_V4L2 参数
camera = cv2.VideoCapture(0, cv2.CAP_V4L2)
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

def generate_frames():
    while True:
        success, frame = camera.read()
        if not success:
            break
        else:
            # 将图像编码为 JPEG，压缩质量设为 80 以减少网络带宽占用
            ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            frame = buffer.tobytes()
            # 使用 MJPEG 协议持续推送画面
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/')
def index():
    # 极简的前端页面
    return '''
    <html>
      <body style="background: #222; color: white; text-align: center; margin-top: 50px; font-family: sans-serif;">
        <h2>智能小车 - OV5647 实时视角</h2>
        <img src="/video_feed" style="border: 2px solid #555; border-radius: 8px; max-width: 100%;">
      </body>
    </html>
    '''

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    # 监听所有网络接口，端口设为 5000
    app.run(host='0.0.0.0', port=5000, threaded=True)
