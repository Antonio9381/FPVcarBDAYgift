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
