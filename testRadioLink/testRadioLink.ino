#define CRSF_TX_PIN 17
#define CRSF_RX_PIN 18
#define INVERT true

uint16_t ch[16];
uint8_t rx[64];
int rxLen = 0, rxNeed = 0;
uint32_t bytesIn = 0, frames = 0, moduleFrames = 0, linkFrames = 0;
uint32_t lastPing = 0, lastReport = 0;

uint32_t echoFrames = 0;


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

void sendChannels() {
  uint8_t f[26] = {0xEE, 24, 0x16};
  uint32_t bitPos = 0;
  for (int i = 0; i < 16; i++)
    for (int b = 0; b < 11; b++, bitPos++)
      if (ch[i] & (1 << b)) f[3 + bitPos / 8] |= 1 << (bitPos % 8);
  f[25] = crc8(f + 2, 23);
  Serial1.write(f, 26);
}

void sendPing() {
  uint8_t f[6] = {0xEE, 4, 0x28, 0xEE, 0xEA, 0};
  f[5] = crc8(f + 2, 3);
  Serial1.write(f, 6);
}

void handleFrame() {
  if (crc8(rx + 2, rx[1] - 1) != rx[rx[1] + 1]) return;
  uint8_t type = rx[2];
  if (rx[0] == 0xEE && (type == 0x16 || type == 0x28)) { echoFrames++; return; }
  frames++;
  if (type == 0x14) linkFrames++;
}

void readTelemetry() {
  while (Serial1.available()) {
    uint8_t b = Serial1.read();
    bytesIn++;
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

void report() {
  if (linkFrames) led(0, 40, 0);
  else if (frames) led(0, 0, 40);
  else if (echoFrames) led(40, 25, 0);
  else if (bytesIn) led(40, 40, 40);
  else led(40, 0, 0);
  bytesIn = frames = linkFrames = echoFrames = 0;
}

void setup() {
  Serial1.begin(400000, SERIAL_8N1, CRSF_RX_PIN, CRSF_TX_PIN, INVERT, true);
  for (int i = 0; i < 16; i++) ch[i] = 992;
  ch[4] = 172;
  led(40, 0, 40);
}

void loop() {
  ch[0] = 992 + 600 * sin(millis() / 1000.0);
  sendChannels();
  if (millis() - lastPing > 1000) { lastPing = millis(); sendPing(); }
  readTelemetry();
  if (millis() - lastReport > 1000) { lastReport = millis(); report(); }
  delay(4);
}