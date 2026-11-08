#define CRSF_TX_PIN 17
#define CRSF_RX_PIN 16
#define LED_PIN 2
#define INVERT true
#define CMD_TIMEOUT_MS 300

uint16_t ch[16];
uint8_t rx[64];
int rxLen = 0, rxNeed = 0;
uint32_t frames = 0, linkFrames = 0, lastReport = 0, lastCmd = 0, lastSend = 0;
char line[32];
int lineLen = 0;
int steer = 0, throttle = 0;
int ledMode = 0;

uint8_t crc8(const uint8_t *d, int n) {
  uint8_t c = 0;
  for (int i = 0; i < n; i++) {
    c ^= d[i];
    for (int b = 0; b < 8; b++) c = (c & 0x80) ? (c << 1) ^ 0xD5 : c << 1;
  }
  return c;
}

uint16_t toCrsf(int v) {
  v = constrain(v, -1000, 1000);
  return 992 + (long)v * 819 / 1000;
}

void sendChannels() {
  uint8_t f[26] = {0xEE, 24, 0x16};
  uint32_t bitPos = 0;
  for (int i = 0; i < 16; i++)
    for (int b = 0; b < 11; b++, bitPos++)
      if (ch[i] & (1 << b)) f[3 + bitPos / 8] |= 1 << (bitPos % 8);
  f[25] = crc8(f + 2, 23);
  Serial2.write(f, 26);
}

void handleFrame() {
  if (crc8(rx + 2, rx[1] - 1) != rx[rx[1] + 1]) return;
  if (rx[0] == 0xEE && rx[2] == 0x16) return;
  frames++;
  if (rx[2] == 0x14) linkFrames++;
}

void readTelemetry() {
  while (Serial2.available()) {
    uint8_t b = Serial2.read();
    if (rxLen == 0) {
      if (b == 0xEA || b == 0xC8 || b == 0xEE) rx[rxLen++] = b;
    } else if (rxLen == 1) {
      if (b < 2 || b > 62) { rxLen = 0; continue; }
      rx[rxLen++] = b;
      rxNeed = b + 2;
    } else {
      rx[rxLen++] = b;
      if (rxLen >= rxNeed) { handleFrame(); rxLen = 0; }
    }
  }
}

void readPc() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n') {
      line[lineLen] = 0;
      int s, t;
      if (sscanf(line, "%d,%d", &s, &t) == 2) {
        steer = s;
        throttle = t;
        lastCmd = millis();
      }
      lineLen = 0;
    } else if (c != '\r' && lineLen < (int)sizeof(line) - 1) {
      line[lineLen++] = c;
    }
  }
}

void report() {
  bool pc = millis() - lastCmd < CMD_TIMEOUT_MS;
  if (linkFrames && pc) ledMode = 3;
  else if (linkFrames) ledMode = 2;
  else if (frames) ledMode = 1;
  else ledMode = 0;
  frames = linkFrames = 0;
}

void updateLed() {
  uint32_t t = millis();
  bool on = false;
  if (ledMode == 3) on = true;
  else if (ledMode == 2) on = (t / 100) % 2;
  else if (ledMode == 1) on = (t / 500) % 2;
  digitalWrite(LED_PIN, on);
}

void setup() {
  Serial.begin(115200);
  Serial2.begin(400000, SERIAL_8N1, CRSF_RX_PIN, CRSF_TX_PIN, INVERT);
  pinMode(LED_PIN, OUTPUT);
  for (int i = 0; i < 16; i++) ch[i] = 992;
  ch[4] = 172;
}

void loop() {
  readPc();
  readTelemetry();
  if (millis() - lastCmd > CMD_TIMEOUT_MS) { steer = 0; throttle = 0; }
  if (millis() - lastSend >= 4) {
    lastSend = millis();
    ch[0] = toCrsf(steer);
    ch[1] = toCrsf(throttle);
    sendChannels();
  }
  if (millis() - lastReport > 500) { lastReport = millis(); report(); }
  updateLed();
}
