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
