import sys
import serial
import serial.tools.list_ports
import pygame

ESP_VIDS = {0x303A, 0x1A86, 0x10C4, 0x0403}
SEND_HZ = 50

STEER_AXIS = 0
GAS_AXIS = 2
BRAKE_AXIS = 3
WHEEL_RANGE_DEG = 900
STEER_LOCK_DEG = 270
STEER_DEADZONE = 0.02
PEDAL_REST = 1.0

REVERSE_STEERING = False
REVERSE_THROTTLE = False


def find_port():
    if len(sys.argv) > 1:
        return sys.argv[1]
    ports = list(serial.tools.list_ports.comports())
    esp = [p for p in ports if p.vid in ESP_VIDS]
    if len(esp) == 1:
        return esp[0].device
    print("No ESP32 found - running in wheel test mode (nothing is sent).")
    print("Available ports:")
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
    return max(0.0, min(1.0, abs(raw - PEDAL_REST) / 2.0))


def steering(raw):
    deg = raw * WHEEL_RANGE_DEG / 2.0
    s = deg / (STEER_LOCK_DEG / 2.0)
    if abs(s) < STEER_DEADZONE:
        s = 0.0
    return max(-1.0, min(1.0, s))


def main():
    port = find_port()
    ser = None
    if port:
        print(f"Using {port}")
        ser = open_port(port)

    pygame.init()
    pygame.joystick.init()
    screen = pygame.display.set_mode((560, 520))
    pygame.display.set_caption("Wheel RC")
    font = pygame.font.Font(None, 28)
    small = pygame.font.Font(None, 22)
    clock = pygame.time.Clock()

    wheel = find_wheel()
    max_throttle = 0.3
    gas_seen_rest = False
    brake_seen_rest = False
    killed = False
    ok_count = 0
    running = True

    while running:
        clock.tick(SEND_HZ)

        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.JOYDEVICEADDED and wheel is None:
                wheel = find_wheel()
            elif e.type == pygame.JOYDEVICEREMOVED:
                wheel = find_wheel() if pygame.joystick.get_count() else None
                gas_seen_rest = brake_seen_rest = False
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    running = False
                elif e.key == pygame.K_SPACE:
                    killed = not killed
                elif e.key in (pygame.K_UP, pygame.K_EQUALS):
                    max_throttle = min(1.0, round(max_throttle + 0.1, 1))
                elif e.key in (pygame.K_DOWN, pygame.K_MINUS):
                    max_throttle = max(0.1, round(max_throttle - 0.1, 1))

        raw_s = axis(wheel, STEER_AXIS)
        raw_g = axis(wheel, GAS_AXIS)
        raw_b = axis(wheel, BRAKE_AXIS)

        if abs(raw_g - PEDAL_REST) < 0.1:
            gas_seen_rest = True
        if abs(raw_b - PEDAL_REST) < 0.1:
            brake_seen_rest = True
        armed = wheel is not None and gas_seen_rest and brake_seen_rest and not killed

        steer = steering(raw_s) if wheel else 0.0
        gas = pedal(raw_g) if gas_seen_rest else 0.0
        brake = pedal(raw_b) if brake_seen_rest else 0.0
        throttle = (gas - brake) * max_throttle if armed else 0.0

        s = -steer if REVERSE_STEERING else steer
        t = -throttle if REVERSE_THROTTLE else throttle
        if send(ser, f"{int(s * 1000)},{int(t * 1000)}\n".encode()):
            ok_count = min(ok_count + 1, 10)
        else:
            ok_count = 0

        screen.fill((20, 22, 28))
        white, grey = (220, 220, 220), (150, 150, 160)
        green, red, amber = (90, 220, 120), (240, 90, 90), (240, 190, 70)

        if wheel is None:
            arm_text, arm_col = "NO WHEEL DETECTED", red
        elif killed:
            arm_text, arm_col = "STOPPED (SPACE to resume)", red
        elif not armed:
            arm_text, arm_col = "Press and release BOTH pedals to arm", amber
        else:
            arm_text, arm_col = "ARMED", green

        rows = [
            (f"Port {port or '-'}", white),
            ("TEST MODE - no ESP32, nothing sent", amber) if ser is None else
            ("ESP32 OK" if ok_count >= 5 else "ESP32 NOT READING - press RST", green if ok_count >= 5 else red),
            (f"Wheel: {wheel.get_name() if wheel else '-'}", white),
            (arm_text, arm_col),
            (f"Steering  {steer:+.2f}", white),
            (f"Gas {gas:.2f}   Brake {brake:.2f}   Throttle {throttle:+.2f}", white),
            (f"Max throttle {max_throttle:.1f}   (Up/Down)", white),
            ("SPACE stop/resume   ESC quit", grey),
        ]
        y = 16
        for text, col in rows:
            screen.blit(font.render(text, True, col), (20, y))
            y += 32

        y += 8
        screen.blit(small.render("Raw axes (to check mapping):", True, grey), (20, y))
        y += 22
        if wheel:
            for i in range(wheel.get_numaxes()):
                tag = {STEER_AXIS: " steer", GAS_AXIS: " gas", BRAKE_AXIS: " brake"}.get(i, "")
                screen.blit(small.render(f"axis {i}: {wheel.get_axis(i):+.2f}{tag}", True, white), (20 + (i % 3) * 180, y + (i // 3) * 20))
            y += ((wheel.get_numaxes() + 2) // 3) * 20 + 6
            pressed = [str(b) for b in range(wheel.get_numbuttons()) if wheel.get_button(b)]
            screen.blit(small.render(f"Buttons: {' '.join(pressed) or '-'}", True, white), (20, y))
        pygame.display.flip()

    for _ in range(5):
        send(ser, b"0,0\n")
    if ser:
        ser.close()
    pygame.quit()


if __name__ == "__main__":
    main()
