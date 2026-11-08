#define CRSF_TX_PIN 17
#define CRSF_RX_PIN 18
#define INVERT true
#define CMD_TIMEOUT_MS 300

uint16_t ch[16];
uint8_t rx[64];
int rxLen = 0, rxNeed = 0;
uint32_t frames = 0, linkFrames = 0, lastReport = 0, lastCmd = 0, lastSend = 0;
char line[32];
int lineLen = 0;
int steer = 0, throttle = 0;

uint8_t crc8(const uint8_t *d, int n) {
  uint8_t c = 0;
  for (int i = 0; i < n; i++) {
    c ^= d[i];
    for (int b = 0; b < 8; b++) c = (c & 0x80) ? (c << 1) ^ 0xD5 : c << 1;
  }
  return c;
}

void led(uint8_t r, uint8_t g, uint8_t b) {
  neopixelWrite(48, r, g, b);
  neopixelWrite(38, r, g, b);
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
  Serial1.write(f, 26);
}

void handleFrame() {
  if (crc8(rx + 2, rx[1] - 1) != rx[rx[1] + 1]) return;
  if (rx[0] == 0xEE && rx[2] == 0x16) return;
  frames++;
  if (rx[2] == 0x14) linkFrames++;
}

void readTelemetry() {
  while (Serial1.available()) {
    uint8_t b = Serial1.read();
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
  if (linkFrames && pc) led(0, 40, 0);
  else if (linkFrames) led(40, 0, 40);
  else if (frames) led(0, 0, 40);
  else led(40, 0, 0);
  frames = linkFrames = 0;
}

void setup() {
  Serial.begin(115200);
  Serial1.begin(400000, SERIAL_8N1, CRSF_RX_PIN, CRSF_TX_PIN, INVERT, true);
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
}
