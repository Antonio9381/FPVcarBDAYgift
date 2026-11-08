# PC-Controlled RC Car over ELRS — Setup Guide

Drive an RC car from a PC (keyboard now, Logitech G920 later) using an ESP32-S3 as a bridge into a RadioMaster Ranger Micro ELRS transmitter, linked to a RadioMaster ER6 PWM receiver in the car.

```
PC (Python, WASD) ──USB──▶ ESP32-S3 ──CRSF (GPIO17/18)──▶ Ranger Micro ~~2.4 GHz~~▶ ER6 ──PWM──▶ servo (CH1) + ESC (CH2)
```

---

## FPV interface software

Debut Video Capture Software

tool -> other option -> webcam -> USB video

## 1. Hardware

| Part | Notes |
|---|---|
| RadioMaster Ranger Micro 2.4 GHz TX | ELRS TX module. Powered via XT30, 6–16 V. **Antenna must be attached before powering** (up to 1 W). |
| RadioMaster ER6 2.4 GHz PWM RX | 6 PWM outputs, 5 V on the servo rail. |
| ESP32-S3 dev board, later an ESP32-WROOM-32D ("ESP-32D") | Bridge PC → CRSF. Switched to the ESP-32D after the S3's USB serial stopped working. |
| 1 kΩ resistor | In series on the ESP32 TX line (half-duplex). |
| 2S/3S LiPo or 6–16 V supply | For the Ranger Micro XT30. |
| Windows PC | ExpressLRS Configurator, Arduino IDE, Python. |

---

## 2. Key facts learned

- **The Ranger Micro's USB-C is for flashing only.** It does not accept control data. Control (CRSF) goes into the bay pins, which is why the ESP32 is needed.
- **Binding uses a binding phrase**, not a bind button. TX and RX connect automatically when they have the same phrase, the same major ELRS version and the same regulatory domain.
- **Versions used:** both on **ELRS 3.3.1**, **2.4 GHz ISM** domain. Do not mix 3.x and 4.x.
- **Binding phrase used:** `naimish-rccar-bday`, which gives UID `96,211,104,244,108,23`.
- **CRSF channel packets always carry 16 channels.** The ER6 outputs CH1–CH6. ELRS sends CH1–CH4 at full resolution, so steering and throttle go on CH1/CH2. Keep **CH5 low**, because ELRS treats it as the arm switch.

---

## 3. Binding the Ranger Micro and ER6

### 3.1 Install ExpressLRS Configurator
Download from the ExpressLRS Configurator GitHub releases. v1.8.4 was used.

### 3.2 Check the ER6 firmware version
1. Power the ER6 with 5 V on the servo rail.
2. Wait about 60 s with no transmitter. The ER6 starts a Wi-Fi hotspot `ExpressLRS RX` (password `expresslrs`).
3. Connect and open `10.0.0.1`. The header shows the version (3.3.1, ISM2G4).

The Configurator shows **"fetch failed"** while you're on the ER6 hotspot, because there's no internet. Ignore it.

### 3.3 Set the binding phrase on the ER6 (no flashing needed)
1. On `10.0.0.1` → **OPTIONS**, type the binding phrase.
2. The badge changes from "Not set" to **"Overridden"** and shows the UID.
3. Click **SAVE**.

To verify the phrase, the UID must read `96,211,104,244,108,23` for `naimish-rccar-bday`. To compute the UID for any phrase:

```python
import hashlib
p = "naimish-rccar-bday"
print(list(hashlib.md5(f'-DMY_BINDING_PHRASE="{p}"'.encode()).digest()[:6]))
```

### 3.4 Flash the Ranger Micro over USB-C
Reconnect the PC to normal internet first. Then set the Configurator to:
- **Version:** 3.3.1
- **Device category:** RadioMaster 2.4 GHz
- **Device:** RadioMaster Ranger Micro 2.4GHz TX
- **Flashing method:** UART (Serial), COM port of the module (was COM5)
- **Regulatory domain:** tick **2.4 GHz ISM (Standard)**
- **Binding phrase:** ticked, `naimish-rccar-bday`
- Leave Wi-Fi, Erase and Force Flash unticked

Click **FLASH**. Ignore the "update Lua script" message, which only applies to handheld radios.

The BUILD button only appears with the **Wi-Fi** flashing method selected. With UART, FLASH builds and flashes in one go.

---

## 4. Wiring the ESP32-S3 to the Ranger Micro

JR bay pin order: **PPM, Battery, GND, (unused), S.Port**. GND is the **middle** pin. The two **end pins** are the signal pins.

```
ESP32-S3 GPIO17 ──[1kΩ]──┬── Ranger signal pin (end pin)
ESP32-S3 GPIO18 ─────────┘
ESP32-S3 GND ──────────────── Ranger GND (middle pin)
XT30 ◀── 6–16 V
```

**Danger:** the pin next to GND carries the full XT30 battery voltage. Never touch it with an ESP32 wire. Check with a multimeter first:
1. Continuity between each pin and XT30 negative: only the middle pin should beep (GND).
2. DC volts on each pin vs GND, with the XT30 powered: one pin reads battery voltage. Avoid it.

**Working configuration:**
- Signal pin: _TODO: top or bottom end pin_
- `INVERT`: _TODO: true or false_
- UART init line that worked:
  ```cpp
  Serial1.begin(400000, SERIAL_8N1, CRSF_RX_PIN, CRSF_TX_PIN, INVERT, true);
  ```
  The 6th argument is the begin timeout, which normally only matters for auto-baud. It's probably not what fixed it, but this is the exact line that worked.

---

## 5. Arduino IDE settings (ESP32-S3)

- **Board:** ESP32S3 Dev Module
- **USB CDC On Boot:** Enabled on the port labelled "USB", Disabled on the port labelled "UART"/"COM"
- **USB Mode:** Hardware CDC and JTAG
- **Press RST after every upload**, especially after uploading in BOOT mode, or the sketch never runs.
- To upload in download mode: hold **BOOT**, tap **RST**, release **BOOT**, then upload.
- After an upload, the COM port number can change. Reselect it.
- Close the Serial Monitor before running the Python script, because both can't hold the COM port.

---

## 6. LED meanings

### ELRS (Ranger Micro / ER6)
| LED | Meaning |
|---|---|
| One orange flash per second (TX) | No handset/CRSF data reaching the module |
| Fading colour (TX) | Transmitting, no receiver connected |
| Solid colour (TX/RX) | Connected; the colour shows the packet rate |
| Slow blink, 500 ms (RX) | Waiting for a transmitter |
| Fast blink (RX/TX) | Wi-Fi mode, after 60 s without a connection. Power-cycle to exit. |

### ESP32 status LED (WASD sketch)
| LED | Meaning |
|---|---|
| 🟢 Green | Linked to the ER6 and receiving PC commands |
| 🟣 Purple | Linked, but no PC commands (COM port or window focus) |
| 🔵 Blue | Ranger Micro answering, no receiver link |
| 🔴 Red | Ranger Micro not responding (pin or inversion) |

---

## 7. Troubleshooting log (what went wrong and why)

| Symptom | Cause / fix |
|---|---|
| Configurator "fetch failed" | PC on the ER6 hotspot with no internet. Harmless. |
| Ranger flashes orange every second | No CRSF from the ESP32. Check pin, inversion and that the sketch is actually running. |
| ESP32 sketch never runs after upload | Press **RST** after upload. |
| Serial Monitor blank | CDC On Boot doesn't match the USB port, or wrong COM port. The onboard RGB LED is a serial-free way to check that code runs. |
| Diagnostic stuck "yellow" | GPIO18 hears the ESP32's own echo. Yellow means the module is silent, not a decode error. |
| Neither device ever goes solid | The ESP32 wasn't reaching the module. Fixed by getting the CRSF link working, then power-cycling the Ranger before the ER6. |
| Devices drop into Wi-Fi mode | 60 s auto-Wi-Fi without a connection. Power the Ranger and ESP32 first, then the ER6 within about 30 s. |
| `could not open port 'COM19'` in Python | The COM number changed. The script now auto-detects the port; otherwise pass the port as an argument. |
| WASD window goes grey / "Not Responding" | Opening the port toggled DTR/RTS, which resets the ESP32-S3 (sometimes into the bootloader). The ESP32 then stopped reading and Python's write blocked. Fixed by opening with DTR/RTS off and a write timeout. If the window shows "ESP32 NOT READING", press RST. |
| ESP32-S3 serial stopped working entirely | Switched to a classic ESP32 (section 9.1b). |
| Script lists only "Standard Serial over Bluetooth" ports | The ESP32 isn't showing up as a COM port at all. Check Device Manager → **Other devices** for a CP2102/CH340 entry with a yellow warning (missing driver: install the Silicon Labs CP210x or WCH CH340 driver). Otherwise, try a data-capable USB cable or another port. |
| One ESP32 USB port stopped powering the board | Possible damage from probing near the battery pin. The chip still worked on the other port. |

---

## 8. Power-up order

1. ESP32 running the sketch (USB to PC).
2. Ranger Micro XT30 plugged in, antenna on. The LED goes from orange to fading colour.
3. ER6 powered within about 30 s. Both LEDs go **solid**.
4. Keep TX and RX about 1 m apart when testing on the bench.

---

## 9. WASD control

### 9.1 ESP32 sketch — `wasd_crsf/wasd_crsf.ino`
Set `INVERT` to the working value. Upload, then press **RST**.

```cpp
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
int steer = 0, throttle = 0, aux3 = -1000;

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
      int s, t, a;
      int n = sscanf(line, "%d,%d,%d", &s, &t, &a);
      if (n >= 2) {
        steer = s;
        throttle = t;
        if (n == 3) aux3 = a;
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
    ch[2] = toCrsf(aux3);
    sendChannels();
  }
  if (millis() - lastReport > 500) { lastReport = millis(); report(); }
}
```

### 9.1b ESP32 (classic, ESP32-WROOM-32D) version — `wasd_crsf_esp32/wasd_crsf_esp32.ino`
Use this sketch if you're on a classic ESP32 dev board instead of the S3. The S3's USB serial became unreliable, so the bridge moved to an ESP-32D.

Differences from the S3 version:
- Uses **Serial2**, with **GPIO17 = TX** (through 1 kΩ) and **GPIO16 = RX**, both to the Ranger signal pin. GND goes to the middle pin.
- No RGB LED. Status is shown on the onboard blue LED (**GPIO2**).
- USB serial goes through the board's CP2102/CH340 chip, so there's no USB CDC setting. Board: **ESP32 Dev Module**.
- If an upload hangs on `Connecting...`, hold **BOOT** until it starts writing.

```
ESP32 GPIO17 ──[1kΩ]──┬── Ranger signal pin (end pin)
ESP32 GPIO16 ─────────┘
ESP32 GND ───────────── Ranger GND (middle pin)
```

| Blue LED (GPIO2) | Meaning |
|---|---|
| Solid on | Linked to the ER6 and receiving PC commands |
| Fast blink | Linked, no PC commands |
| Slow blink | Ranger Micro answering, no receiver link |
| Off | Ranger Micro silent (pin or `INVERT`) |

If the LED stays off, flip `INVERT` and power-cycle the Ranger Micro. If it's still off, move both GPIO wires to the other end pin.

```cpp
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
int steer = 0, throttle = 0, aux3 = -1000;
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
      int s, t, a;
      int n = sscanf(line, "%d,%d,%d", &s, &t, &a);
      if (n >= 2) {
        steer = s;
        throttle = t;
        if (n == 3) aux3 = a;
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
    ch[2] = toCrsf(aux3);
    sendChannels();
  }
  if (millis() - lastReport > 500) { lastReport = millis(); report(); }
  updateLed();
}
```

### 9.2 PC script — `wasd_drive.py`
Install with `pip install pyserial pygame`, then run `py wasd_drive.py`. It finds the ESP32's port automatically. If it can't, it lists the available ports, and you run `py wasd_drive.py COMx` with the right one.

List ports manually with `py -m serial.tools.list_ports -v`. The COM number changes between uploads and USB ports.

```python
import sys
import serial
import serial.tools.list_ports
import pygame

ESP_VIDS = {0x303A, 0x1A86, 0x10C4, 0x0403}
SEND_HZ = 50
STEER_RATE = 4.0
REVERSE_STEERING = False
REVERSE_THROTTLE = False


def find_port():
    if len(sys.argv) > 1:
        return sys.argv[1]
    ports = list(serial.tools.list_ports.comports())
    esp = [p for p in ports if p.vid in ESP_VIDS]
    if len(esp) == 1:
        return esp[0].device
    print("Could not pick a port automatically. Available ports:")
    for p in ports:
        print(f"  {p.device:8} {p.description}")
    print("Run: py wasd_drive.py COMx")
    sys.exit(1)


def open_port(port):
    ser = serial.Serial()
    ser.port = port
    ser.baudrate = 115200
    ser.timeout = 0
    ser.write_timeout = 0.02
    ser.dtr = False
    ser.rts = False
    ser.open()
    return ser


def send(ser, msg):
    try:
        ser.write(msg)
        return True
    except serial.SerialTimeoutException:
        ser.reset_output_buffer()
        return False
    except serial.SerialException:
        return False


def main():
    port = find_port()
    print(f"Using {port}")
    ser = open_port(port)

    pygame.init()
    screen = pygame.display.set_mode((460, 250))
    pygame.display.set_caption("WASD RC")
    font = pygame.font.Font(None, 30)
    clock = pygame.time.Clock()

    steer = 0.0
    max_throttle = 0.3
    ok_count = 0
    running = True

    while running:
        dt = clock.tick(SEND_HZ) / 1000.0

        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    running = False
                elif e.key in (pygame.K_UP, pygame.K_EQUALS):
                    max_throttle = min(1.0, round(max_throttle + 0.1, 1))
                elif e.key in (pygame.K_DOWN, pygame.K_MINUS):
                    max_throttle = max(0.1, round(max_throttle - 0.1, 1))

        k = pygame.key.get_pressed()
        target = k[pygame.K_d] - k[pygame.K_a]
        step = STEER_RATE * dt
        steer += max(-step, min(step, target - steer))

        throttle = (k[pygame.K_w] - k[pygame.K_s]) * max_throttle
        if k[pygame.K_SPACE]:
            throttle = 0.0

        s = -steer if REVERSE_STEERING else steer
        t = -throttle if REVERSE_THROTTLE else throttle
        if send(ser, f"{int(s * 1000)},{int(t * 1000)}\n".encode()):
            ok_count = min(ok_count + 1, 10)
        else:
            ok_count = 0

        screen.fill((20, 22, 28))
        status = ("ESP32 OK", (90, 220, 120)) if ok_count >= 5 else ("ESP32 NOT READING - press RST", (240, 90, 90))
        rows = [
            (f"Port      {port}", (220, 220, 220)),
            status,
            (f"Steering  {steer:+.2f}", (220, 220, 220)),
            (f"Throttle  {throttle:+.2f}", (220, 220, 220)),
            (f"Max thr   {max_throttle:.1f}   (Up/Down)", (220, 220, 220)),
            ("WASD drive  SPACE stop  ESC quit", (150, 150, 160)),
        ]
        for i, (r, c) in enumerate(rows):
            screen.blit(font.render(r, True, c), (20, 20 + i * 36))
        pygame.display.flip()

    for _ in range(5):
        send(ser, b"0,0\n")
    ser.close()
    pygame.quit()


if __name__ == "__main__":
    main()
```

### 9.3 Controls
| Key | Action |
|---|---|
| W / S | Forward / reverse |
| A / D | Steer |
| Space | Stop |
| Up / Down | Max throttle ±10% (starts at 30%) |
| Esc | Quit (sends stop) |

### 9.4 Safety
- If no PC command arrives for 300 ms, the ESP32 centres the steering and sets the throttle to zero.
- Test with the wheels off the ground first.
- If steering or throttle is backwards, set `REVERSE_STEERING` / `REVERSE_THROTTLE` in the Python file.
- Many car ESCs need a double-tap for reverse: the first press brakes, then release and press again.
- Set the ER6 failsafe (web UI) to fixed positions with neutral throttle.

---

## 10. Driving with the Logitech G29 wheel and pedals

Hardware: Logitech G29 Driving Force (PlayStation version) with pedals, over USB. The ESP32 runs the same bridge sketch (section 9). The PC runs `wheel_drive.py`.

The PC sends `steer,throttle,ch3` lines (each -1000…1000) to the ESP32, which maps them to CH1, CH2 and CH3. The ESP32 sketches still accept the old 2-value WASD lines.

### 10.1 Setup
1. Plug in the wheel. It does its calibration spin.
2. Optional: in Logitech G HUB, set the operating range to **900°** to match `WHEEL_RANGE_DEG`. G HUB's centering spring gives some self-centre feel.
3. Check the wheel works in `joy.cpl` (Win+R → `joy.cpl` → Properties).
4. Close anything else using the wheel, and Arduino's Serial Monitor.
5. Run `py wheel_drive.py` (or `py wheel_drive.py COMx`). With no ESP32 plugged in, it runs in **test mode**: everything works on screen but nothing is sent.

### 10.2 Axis and button mapping (confirmed on this PC)
| Function | Index | Setting |
|---|---|---|
| Steering | axis 0 | `STEER_AXIS` |
| Gas | axis 2 | `GAS_AXIS` |
| Brake | axis 3 | `BRAKE_AXIS` |
| Forward gear | button 4 | `BTN_FORWARD` |
| Reverse gear | button 5 | `BTN_REVERSE` |
| Lights (CH3) | button 11 | `BTN_LIGHTS` |

Pedals rest at about +1 and read -1 when fully pressed (`PEDAL_REST = 1.0`). The window's bottom rows show raw axes and pressed buttons, for re-checking.

### 10.3 Realistic driving model
- **Gears:** the car starts in **N**. Button 4 toggles **D** (press again for N). Button 5 toggles **R** (press again for N). In N, the pedals do nothing.
- **Gas:** goes through the throttle curve, then a ramp (`ACCEL_RATE` up, `DECEL_RATE` down), which gives the car a feeling of inertia instead of instant power.
- **Brake (in D):** sends negative throttle proportional to the pedal (up to `BRAKE_MAX`). With a forward/brake/reverse ESC, that's real braking. When you release the brake, the script sends a tiny forward blip (`FWD_BLIP`) so the ESC doesn't treat the next brake press as "go reverse".
- **Brake (in R):** cuts the drive to neutral, so the car coasts or drag-brakes. Sending forward throttle here would make it accelerate forwards instead of braking.
- **Shifting into R** (`ESC_MODE = "fbr"`): the script does the ESC double-tap for you automatically (brief brake pulse, neutral, then reverse is available). Reverse speed is capped at `REVERSE_MAX`.
- If your ESC reverses instantly with no double-tap (crawler-style), set `ESC_MODE = "fr"`.
- **Lights:** button 11 (or key L) toggles CH3 between full low and full high. The ER6's CH3 needs an **RC light controller / PWM switch** in between; an ER6 signal pin can't power LEDs directly.

### 10.4 Rates (drone-style)
Throttle uses a Betaflight-style **mid + expo** curve. Steering uses **rate + expo**. The curve is drawn live on screen with your current pedal position.

| Setting | Keys | Effect |
|---|---|---|
| Max throttle | Up / Down | Top output (power limit) |
| Throttle expo | Left / Right | Softer around the mid point |
| Throttle mid | `[` / `]` | Where the curve's flat spot sits |
| Steer rate | `;` / `'` | Max steering throw |
| Steer expo | `,` / `.` | Softer near centre, full at lock |
| Save / reset | `S` / `0` | Saved to `rates.json` next to the script (also on exit) |

Starting point: max throttle 0.4, mid 0.5, expo 0.3, steer rate 1.0, steer expo 0.2.

### 10.5 Other controls and safety
| Input | Action |
|---|---|
| F / R / N keys | Gear (keyboard fallback) |
| L | Lights |
| Space | Emergency stop (forces N, toggles) |
| Esc | Quit (sends stop, lights off, saves rates) |

- **Arming:** nothing moves until both pedals have been seen at rest after starting. Press and release both once.
- If the wheel is unplugged, it drops to N and disarms. If the script stops, the ESP32 cuts throttle and steering after 300 ms (the lights keep their last state).
- Test with the wheels off the ground first. If braking makes the car reverse, raise `FWD_BLIP` slightly (the ESC deadband is eating it) or set the ESC to forward/brake/reverse mode.

### 10.6 `wheel_drive.py`

```python
import json
import os
import sys
import time
import serial
import serial.tools.list_ports
import pygame

ESP_VIDS = {0x303A, 0x1A86, 0x10C4, 0x0403}
SEND_HZ = 50

STEER_AXIS = 0
GAS_AXIS = 2
BRAKE_AXIS = 3
BTN_FORWARD = 4
BTN_REVERSE = 5
BTN_LIGHTS = 11

WHEEL_RANGE_DEG = 900
STEER_LOCK_DEG = 270
STEER_DEADZONE = 0.02
PEDAL_REST = 1.0
PEDAL_DEADZONE = 0.03

ESC_MODE = "fbr"
BRAKE_MAX = 0.6
REVERSE_MAX = 0.5
ACCEL_RATE = 1.2
DECEL_RATE = 3.0
REVERSE_ARM_PULSE = 0.25
REVERSE_ARM_MS = 120
FWD_BLIP = 0.08
FWD_BLIP_MS = 60

REVERSE_STEERING = False
REVERSE_THROTTLE = False

RATES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rates.json")
DEFAULT_RATES = {"max_throttle": 0.4, "thr_mid": 0.5, "thr_expo": 0.3, "steer_rate": 1.0, "steer_expo": 0.2}
LIMITS = {"max_throttle": (0.05, 1.0), "thr_mid": (0.1, 0.9), "thr_expo": (0.0, 1.0), "steer_rate": (0.2, 1.0), "steer_expo": (0.0, 1.0)}
KEY_ADJUST = {
    pygame.K_UP: ("max_throttle", 0.05),
    pygame.K_DOWN: ("max_throttle", -0.05),
    pygame.K_RIGHT: ("thr_expo", 0.05),
    pygame.K_LEFT: ("thr_expo", -0.05),
    pygame.K_RIGHTBRACKET: ("thr_mid", 0.05),
    pygame.K_LEFTBRACKET: ("thr_mid", -0.05),
    pygame.K_PERIOD: ("steer_expo", 0.05),
    pygame.K_COMMA: ("steer_expo", -0.05),
    pygame.K_QUOTE: ("steer_rate", 0.05),
    pygame.K_SEMICOLON: ("steer_rate", -0.05),
}


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def find_port():
    if len(sys.argv) > 1:
        return sys.argv[1]
    ports = list(serial.tools.list_ports.comports())
    esp = [p for p in ports if p.vid in ESP_VIDS]
    if len(esp) == 1:
        return esp[0].device
    print("No ESP32 found - running in wheel test mode (nothing is sent).")
    for p in ports:
        print(f"  {p.device:8} {p.description}")
    return None


def open_port(port):
    ser = serial.Serial()
    ser.port = port
    ser.baudrate = 115200
    ser.timeout = 0
    ser.write_timeout = 0.02
    ser.dtr = False
    ser.rts = False
    ser.open()
    return ser


def send(ser, msg):
    if ser is None:
        return False
    try:
        ser.write(msg)
        return True
    except serial.SerialTimeoutException:
        ser.reset_output_buffer()
        return False
    except serial.SerialException:
        return False


def load_rates():
    rates = dict(DEFAULT_RATES)
    try:
        with open(RATES_FILE) as f:
            rates.update({k: float(v) for k, v in json.load(f).items() if k in rates})
    except (OSError, ValueError):
        pass
    return rates


def save_rates(rates):
    try:
        with open(RATES_FILE, "w") as f:
            json.dump({k: round(v, 2) for k, v in rates.items()}, f, indent=2)
        return True
    except OSError:
        return False


def find_wheel():
    best = None
    for i in range(pygame.joystick.get_count()):
        js = pygame.joystick.Joystick(i)
        name = js.get_name().lower()
        if "g29" in name or "logitech" in name or "driving force" in name:
            return js
        if best is None:
            best = js
    return best


def axis(js, i):
    if js is None or i >= js.get_numaxes():
        return 0.0
    return js.get_axis(i)


def pedal(raw):
    v = clamp(abs(raw - PEDAL_REST) / 2.0, 0.0, 1.0)
    return 0.0 if v < PEDAL_DEADZONE else v


def steering(raw):
    s = raw * WHEEL_RANGE_DEG / STEER_LOCK_DEG
    return 0.0 if abs(s) < STEER_DEADZONE else clamp(s, -1.0, 1.0)


def throttle_curve(x, mid, expo):
    if x <= 0:
        return 0.0
    span = mid if x < mid else 1.0 - mid
    t = (x - mid) / span
    return clamp(mid + span * t * (1.0 - expo + expo * t * t), 0.0, 1.0)


def steer_curve(x, rate, expo):
    return clamp((x * (1.0 - expo) + x ** 3 * expo) * rate, -1.0, 1.0)


class Drivetrain:
    def __init__(self):
        self.gear = "N"
        self.drive = 0.0
        self.seq = []
        self.was_braking = False

    def shift(self, gear):
        now = time.monotonic()
        self.gear = gear
        self.drive = 0.0
        self.seq = []
        if gear == "R" and ESC_MODE == "fbr":
            t = REVERSE_ARM_MS / 1000.0
            self.seq = [(-REVERSE_ARM_PULSE, now + t, "arming reverse"), (0.0, now + 2 * t, "arming reverse")]

    def phase(self):
        return self.seq[0][2] if self.seq else ""

    def update(self, gas, brake, dt, rates):
        now = time.monotonic()
        braking = brake > 0.0
        target = 0.0
        if self.gear != "N" and not braking:
            target = throttle_curve(gas, rates["thr_mid"], rates["thr_expo"]) * rates["max_throttle"]
        step = (ACCEL_RATE if target > self.drive else DECEL_RATE) * dt
        self.drive += clamp(target - self.drive, -step, step)

        if self.gear == "D" and ESC_MODE == "fbr" and self.was_braking and not braking:
            self.seq = [(FWD_BLIP, now + FWD_BLIP_MS / 1000.0, "brake release")]
        self.was_braking = braking

        self.seq = [s for s in self.seq if s[1] > now]
        if self.seq:
            return self.seq[0][0]
        if self.gear == "D":
            return -brake * BRAKE_MAX if braking else self.drive
        if self.gear == "R":
            return 0.0 if braking else -min(self.drive, REVERSE_MAX)
        return 0.0


def bar(screen, font, rect, value, color, label, centered=False):
    pygame.draw.rect(screen, (40, 44, 54), rect, border_radius=4)
    if centered:
        mid = rect.x + rect.w / 2
        w = value * rect.w / 2
        fill = pygame.Rect(min(mid, mid + w), rect.y, abs(w), rect.h)
        pygame.draw.line(screen, (90, 90, 100), (mid, rect.y), (mid, rect.bottom))
    else:
        fill = pygame.Rect(rect.x, rect.y, value * rect.w, rect.h)
    pygame.draw.rect(screen, color, fill, border_radius=4)
    screen.blit(font.render(label, True, (190, 190, 200)), (rect.x, rect.y - 20))


def draw_curve(screen, font, rect, rates, gas):
    pygame.draw.rect(screen, (34, 38, 48), rect, border_radius=6)
    for i in range(1, 4):
        x = rect.x + rect.w * i / 4
        y = rect.y + rect.h * i / 4
        pygame.draw.line(screen, (48, 52, 64), (x, rect.y), (x, rect.bottom))
        pygame.draw.line(screen, (48, 52, 64), (rect.x, y), (rect.right, y))
    pts = []
    for i in range(61):
        u = i / 60
        y = throttle_curve(u, rates["thr_mid"], rates["thr_expo"]) * rates["max_throttle"]
        pts.append((rect.x + u * rect.w, rect.bottom - y * rect.h))
    pygame.draw.lines(screen, (90, 170, 255), False, pts, 3)
    cy = throttle_curve(gas, rates["thr_mid"], rates["thr_expo"]) * rates["max_throttle"]
    pygame.draw.circle(screen, (255, 200, 80), (int(rect.x + gas * rect.w), int(rect.bottom - cy * rect.h)), 6)
    screen.blit(font.render("Throttle curve (pedal -> output)", True, (190, 190, 200)), (rect.x, rect.y - 20))


def main():
    port = find_port()
    ser = None
    if port:
        print(f"Using {port}")
        ser = open_port(port)
    rates = load_rates()

    pygame.init()
    pygame.joystick.init()
    screen = pygame.display.set_mode((800, 560))
    pygame.display.set_caption("Wheel RC")
    huge = pygame.font.Font(None, 140)
    font = pygame.font.Font(None, 28)
    small = pygame.font.Font(None, 22)
    clock = pygame.time.Clock()

    wheel = find_wheel()
    car = Drivetrain()
    lights = False
    killed = False
    gas_rest = brake_rest = False
    ok_count = 0
    toast, toast_until = "", 0.0
    running = True

    while running:
        dt = clock.tick(SEND_HZ) / 1000.0

        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.JOYDEVICEADDED and wheel is None:
                wheel = find_wheel()
            elif e.type == pygame.JOYDEVICEREMOVED:
                wheel = find_wheel() if pygame.joystick.get_count() else None
                gas_rest = brake_rest = False
                car.shift("N")
            elif e.type == pygame.JOYBUTTONDOWN:
                if e.button == BTN_FORWARD:
                    car.shift("N" if car.gear == "D" else "D")
                elif e.button == BTN_REVERSE:
                    car.shift("N" if car.gear == "R" else "R")
                elif e.button == BTN_LIGHTS:
                    lights = not lights
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    running = False
                elif e.key == pygame.K_SPACE:
                    killed = not killed
                    car.shift("N")
                elif e.key == pygame.K_l:
                    lights = not lights
                elif e.key == pygame.K_f:
                    car.shift("D")
                elif e.key == pygame.K_r:
                    car.shift("R")
                elif e.key == pygame.K_n:
                    car.shift("N")
                elif e.key == pygame.K_s:
                    toast = "Rates saved" if save_rates(rates) else "Save failed"
                    toast_until = time.monotonic() + 2
                elif e.key == pygame.K_0:
                    rates.update(DEFAULT_RATES)
                    toast, toast_until = "Rates reset", time.monotonic() + 2
                elif e.key in KEY_ADJUST:
                    k, d = KEY_ADJUST[e.key]
                    rates[k] = round(clamp(rates[k] + d, *LIMITS[k]), 2)

        raw_s = axis(wheel, STEER_AXIS)
        raw_g = axis(wheel, GAS_AXIS)
        raw_b = axis(wheel, BRAKE_AXIS)
        if abs(raw_g - PEDAL_REST) < 0.1:
            gas_rest = True
        if abs(raw_b - PEDAL_REST) < 0.1:
            brake_rest = True
        armed = wheel is not None and gas_rest and brake_rest and not killed

        steer = steer_curve(steering(raw_s), rates["steer_rate"], rates["steer_expo"]) if wheel else 0.0
        gas = pedal(raw_g) if armed else 0.0
        brake = pedal(raw_b) if armed else 0.0
        out = car.update(gas, brake, dt, rates) if armed else 0.0
        if not armed:
            car.drive = 0.0

        s = -steer if REVERSE_STEERING else steer
        t = -out if REVERSE_THROTTLE else out
        msg = f"{int(s * 1000)},{int(t * 1000)},{1000 if lights else -1000}\n"
        if send(ser, msg.encode()):
            ok_count = min(ok_count + 1, 10)
        else:
            ok_count = 0

        white, grey = (220, 220, 220), (140, 140, 155)
        green, red, amber, blue = (90, 220, 120), (240, 90, 90), (240, 190, 70), (90, 170, 255)
        screen.fill((20, 22, 28))

        if ser is None:
            link = ("TEST MODE - no ESP32", amber)
        elif ok_count >= 5:
            link = (f"ESP32 OK  ({port})", green)
        else:
            link = ("ESP32 NOT READING - press RST", red)
        if wheel is None:
            arm = ("NO WHEEL", red)
        elif killed:
            arm = ("STOPPED - SPACE to resume", red)
        elif not armed:
            arm = ("Press + release both pedals", amber)
        else:
            arm = ("ARMED", green)
        screen.blit(font.render(link[0], True, link[1]), (20, 14))
        screen.blit(font.render(arm[0], True, arm[1]), (20, 42))
        screen.blit(small.render(wheel.get_name() if wheel else "", True, grey), (20, 70))

        gear_col = {"D": green, "R": red, "N": grey}[car.gear]
        screen.blit(huge.render(car.gear, True, gear_col), (34, 96))
        screen.blit(small.render("GEAR", True, grey), (40, 196))
        light_col = amber if lights else (60, 60, 70)
        pygame.draw.circle(screen, light_col, (190, 150), 26)
        screen.blit(small.render("LIGHTS", True, light_col), (164, 182))
        if car.phase():
            screen.blit(small.render(f"ESC: {car.phase()}", True, blue), (130, 210))

        bar(screen, small, pygame.Rect(20, 260, 360, 18), steer, blue, f"Steering {steer:+.2f}", True)
        bar(screen, small, pygame.Rect(20, 310, 360, 18), gas, green, f"Gas pedal {gas:.2f}")
        bar(screen, small, pygame.Rect(20, 360, 360, 18), brake, red, f"Brake pedal {brake:.2f}")
        bar(screen, small, pygame.Rect(20, 410, 360, 18), out, amber, f"ESC output {out:+.2f}", True)

        draw_curve(screen, small, pygame.Rect(420, 40, 360, 220), rates, gas)
        rate_rows = [
            f"Max throttle {rates['max_throttle']:.2f}   Up/Down",
            f"Throttle expo {rates['thr_expo']:.2f}   Left/Right",
            f"Throttle mid {rates['thr_mid']:.2f}   [ / ]",
            f"Steer rate {rates['steer_rate']:.2f}   ; / '",
            f"Steer expo {rates['steer_expo']:.2f}   , / .",
            "S save   0 reset rates",
        ]
        for i, r in enumerate(rate_rows):
            screen.blit(small.render(r, True, white if i < 5 else grey), (420, 276 + i * 24))

        help_rows = [
            f"Btn {BTN_FORWARD} forward   Btn {BTN_REVERSE} reverse   Btn {BTN_LIGHTS} lights",
            "Keys: F/R/N gear   L lights   SPACE stop   ESC quit",
        ]
        for i, r in enumerate(help_rows):
            screen.blit(small.render(r, True, grey), (20, 450 + i * 22))

        if wheel:
            axes = "  ".join(f"a{i} {wheel.get_axis(i):+.2f}" for i in range(wheel.get_numaxes()))
            pressed = " ".join(str(b) for b in range(wheel.get_numbuttons()) if wheel.get_button(b))
            screen.blit(small.render(axes, True, grey), (20, 506))
            screen.blit(small.render(f"Buttons: {pressed or '-'}", True, grey), (20, 528))

        if toast and time.monotonic() < toast_until:
            screen.blit(font.render(toast, True, amber), (420, 14))
        pygame.display.flip()

    for _ in range(5):
        send(ser, b"0,0,-1000\n")
    save_rates(rates)
    if ser:
        ser.close()
    pygame.quit()


if __name__ == "__main__":
    main()
```

## 11. Next steps
- [ ] Fill in the working signal pin and `INVERT` value in section 4
- [ ] Set the ER6 failsafe positions
- [ ] Wire the steering servo to CH1 and the ESC to CH2, and test
- [x] Wheel control script for the Logitech G29 (section 10)
- [x] G29 mapping confirmed (section 10.2)
- [x] Gears, braking, lights on CH3, throttle/steer rates
- [ ] Wire a light controller to ER6 CH3
- [ ] Tune rates and the ESC brake/reverse feel on the real car
- [ ] Add the 5.8 GHz FPV camera and USB receiver
