/*
 * WTVB01-485 Vibration Sensor Monitor - Arduino Display
 * 
 * PC로부터 시리얼 통신으로 합성 Velocity와 상태 코드를 수신하여
 * 16x2 I2C LCD와 RGB LED로 표시
 * 
 * 프로토콜: <V:값,S:상태>\n
 * 예: <V:1.234,S:1>\n
 * 
 * 상태 코드:
 *   0 = 미연결
 *   1 = 정상
 *   2 = 경고
 *   3 = 위험
 * 
 * 하드웨어:
 *   - 16x2 I2C LCD (주소: 0x27 또는 0x3F)
 *   - RGB LED: RED=7, GREEN=6, BLUE=5
 */

#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// ===== 핀 설정 =====
#define LED_RED   7
#define LED_GREEN 6
#define LED_BLUE  5

// ===== LCD 설정 =====
// I2C 주소가 0x3F인 경우 아래 줄로 변경
LiquidCrystal_I2C lcd(0x27, 16, 2);
// LiquidCrystal_I2C lcd(0x3F, 16, 2);

// ===== 상태 코드 정의 =====
#define STATUS_DISCONNECTED 0
#define STATUS_NORMAL       1
#define STATUS_WARNING      2
#define STATUS_ANOMALY      3

// ===== 전역 변수 =====
String inputBuffer = "";
float currentVelocity = 0.0;
int currentStatus = STATUS_DISCONNECTED;
unsigned long lastReceiveTime = 0;
const unsigned long TIMEOUT_MS = 5000;  // 5초 동안 수신 없으면 미연결 처리

// ===== 상태별 텍스트 =====
const char* statusText[] = {
  "Disconnected",   // 0: 미연결
  "Normal",         // 1: 정상
  "Warning",        // 2: 경고
  "DANGER!"         // 3: 위험
};

void setup() {
  // 시리얼 통신 초기화
  Serial.begin(9600);
  
  // LED 핀 설정
  pinMode(LED_RED, OUTPUT);
  pinMode(LED_GREEN, OUTPUT);
  pinMode(LED_BLUE, OUTPUT);
  
  // LED 초기화 (모두 끔)
  setLEDColor(0, 0, 0);
  
  // LCD 초기화
  lcd.init();
  lcd.backlight();
  lcd.clear();
  
  // 시작 메시지
  lcd.setCursor(0, 0);
  lcd.print("Vibration Sensor");
  lcd.setCursor(0, 1);
  lcd.print("Waiting...");
  
  // 초기 상태: 파란색 LED (대기 중)
  setLEDColor(0, 0, 255);
  
  delay(1000);
}

void loop() {
  // 시리얼 데이터 수신
  while (Serial.available()) {
    char c = Serial.read();
    
    if (c == '\n') {
      // 패킷 완료, 파싱 시도
      parsePacket(inputBuffer);
      inputBuffer = "";
    } else {
      inputBuffer += c;
      
      // 버퍼 오버플로우 방지
      if (inputBuffer.length() > 50) {
        inputBuffer = "";
      }
    }
  }
  
  // 타임아웃 체크 (일정 시간 동안 수신 없으면 미연결 처리)
  if (millis() - lastReceiveTime > TIMEOUT_MS && currentStatus != STATUS_DISCONNECTED) {
    currentStatus = STATUS_DISCONNECTED;
    currentVelocity = 0.0;
    updateDisplay();
  }
}

// ===== 패킷 파싱 =====
void parsePacket(String packet) {
  // 프로토콜: <V:값,S:상태>
  // 예: <V:1.234,S:1>
  
  // 시작/끝 마커 확인
  if (!packet.startsWith("<") || !packet.endsWith(">")) {
    return;
  }
  
  // 마커 제거
  packet = packet.substring(1, packet.length() - 1);
  
  // V: 찾기
  int vIndex = packet.indexOf("V:");
  int commaIndex = packet.indexOf(",");
  int sIndex = packet.indexOf("S:");
  
  if (vIndex == -1 || commaIndex == -1 || sIndex == -1) {
    return;
  }
  
  // 값 추출
  String velocityStr = packet.substring(vIndex + 2, commaIndex);
  String statusStr = packet.substring(sIndex + 2);
  
  // 변환
  float velocity = velocityStr.toFloat();
  int status = statusStr.toInt();
  
  // 유효성 검사
  if (status < 0 || status > 3) {
    return;
  }
  
  // 값 저장
  currentVelocity = velocity;
  currentStatus = status;
  lastReceiveTime = millis();
  
  // 디스플레이 업데이트
  updateDisplay();
}

// ===== 디스플레이 업데이트 =====
void updateDisplay() {
  // LCD 업데이트
  lcd.clear();
  
  // 첫번째 줄: Velocity
  lcd.setCursor(0, 0);
  lcd.print("V: ");
  lcd.print(currentVelocity, 3);
  lcd.print(" mm/s");
  
  // 두번째 줄: 상태
  lcd.setCursor(0, 1);
  lcd.print("S: ");
  lcd.print(statusText[currentStatus]);
  
  // LED 색상 업데이트
  updateLED();
}

// ===== LED 색상 업데이트 =====
void updateLED() {
  switch (currentStatus) {
    case STATUS_DISCONNECTED:
      // 미연결: 파란색
      setLEDColor(0, 0, 255);
      break;
      
    case STATUS_NORMAL:
      // 정상: 초록색
      setLEDColor(0, 255, 0);
      break;
      
    case STATUS_WARNING:
      // 경고: 노란색 (빨강 + 초록)
      setLEDColor(255, 255, 0);
      break;
      
    case STATUS_ANOMALY:
      // 위험: 빨간색
      setLEDColor(255, 0, 0);
      break;
      
    default:
      // 알 수 없음: 모두 끔
      setLEDColor(0, 0, 0);
      break;
  }
}

// ===== RGB LED 색상 설정 =====
void setLEDColor(int red, int green, int blue) {
  // Common Cathode RGB LED 기준
  // Common Anode인 경우 255에서 빼기: analogWrite(LED_RED, 255 - red);
  
  // 디지털 출력 (ON/OFF만 사용)
  digitalWrite(LED_RED, red > 0 ? HIGH : LOW);
  digitalWrite(LED_GREEN, green > 0 ? HIGH : LOW);
  digitalWrite(LED_BLUE, blue > 0 ? HIGH : LOW);
  
  // PWM 출력을 원하면 아래 코드 사용 (핀이 PWM 지원 시)
  // analogWrite(LED_RED, red);
  // analogWrite(LED_GREEN, green);
  // analogWrite(LED_BLUE, blue);
}
