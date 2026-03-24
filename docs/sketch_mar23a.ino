// CNC Shield V3 核心引脚定义
#define EN_PIN    8  // 步进电机全局使能引脚 (低电平启动)

#define X_DIR     5  // X轴 方向控制引脚
#define X_STP     2  // X轴 步进(脉冲)控制引脚

#define Y_DIR     6  // Y轴 方向控制引脚
#define Y_STP     3  // Y轴 步进(脉冲)控制引脚

#define Z_DIR     7  // Z轴 方向控制引脚
#define Z_STP     4  // Z轴 步进(脉冲)控制引脚

void setup() {
  // 1. 将所有控制引脚设置为输出模式
  pinMode(EN_PIN, OUTPUT);
  pinMode(X_DIR, OUTPUT); pinMode(X_STP, OUTPUT);
  pinMode(Y_DIR, OUTPUT); pinMode(Y_STP, OUTPUT);
  pinMode(Z_DIR, OUTPUT); pinMode(Z_STP, OUTPUT);

  // 2. 激活驱动器：将 EN 引脚拉低，通电锁死电机
  digitalWrite(EN_PIN, LOW);

  // 3. 设置初始旋转方向 (HIGH 或 LOW 代表正反转)
  digitalWrite(X_DIR, HIGH);
  digitalWrite(Y_DIR, HIGH);
  digitalWrite(Z_DIR, HIGH);
}

void loop() {
  // 4. 发送脉冲让电机转动 (这里让三个电机同时转)
  digitalWrite(X_STP, HIGH);
  digitalWrite(Y_STP, HIGH);
  digitalWrite(Z_STP, HIGH);
  
  // 脉冲高电平持续时间，这个数值决定了转速。数值越小，转速越快。
  // TMC2209 在 256 细分下非常平滑，800 微秒是一个适中的测试速度。
  delayMicroseconds(800); 

  digitalWrite(X_STP, LOW);
  digitalWrite(Y_STP, LOW);
  digitalWrite(Z_STP, LOW);
  
  // 脉冲低电平持续时间
  delayMicroseconds(800);
}