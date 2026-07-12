"""SET_SLOT_CONFIG byte5(direction/type) 및 all-black 프레임 거부 여부 실험.

usage: python tools/led_param_exp.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.hidpp import HidppError
from src.ledctl import Rs50Led, OFF, GREEN

DIM = (8, 8, 8)


def try_write(led, colors, byte5, label):
    try:
        led.write_frame(colors, direction=byte5)
        print(f"  byte5={byte5} {label}: OK")
        return True
    except HidppError as e:
        print(f"  byte5={byte5} {label}: HID++ err {e.code}")
        return False
    except TimeoutError:
        print(f"  byte5={byte5} {label}: timeout")
        return False


def main():
    led = Rs50Led(slot=4, min_interval=0.0)
    led.backup()
    print(f"백업: byte5={led._saved[1]}")

    green = [GREEN] * 10
    black = [OFF] * 10
    dim = [DIM] * 10

    print("\n[1] 유색 프레임 x byte5 스캔:")
    ok5 = []
    for b5 in (0, 1, 2, 3, 4, 5):
        if try_write(led, green, b5, "green"):
            ok5.append(b5)
        time.sleep(0.15)

    print("\n[2] all-black x 성공한 byte5:")
    for b5 in ok5[:2]:
        try_write(led, black, b5, "black")
        time.sleep(0.15)

    print("\n[3] 거의-black(8,8,8) x 성공한 byte5:")
    for b5 in ok5[:1]:
        try_write(led, dim, b5, "dim")
        time.sleep(0.15)

    print("\n복원...")
    led.restore()
    print("완료")


if __name__ == "__main__":
    main()
