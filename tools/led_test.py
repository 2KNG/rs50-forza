"""RS50 LED 실기 테스트 — 슬롯 4(CUSTOM 5) 백업 후 스윕/블링크 시연, 복원.

usage: python tools/led_test.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ledctl import Rs50Led


def main():
    led = Rs50Led(slot=4, min_interval=0.0)
    print("슬롯 4 기존 설정 백업...")
    led.backup()
    print(f"  백업됨: dir={led._saved[1]} colors={led._saved[2]}")

    try:
        print("1) 전체 소등")
        led.write_frame(led.frame_for_ratio(0))
        time.sleep(0.7)

        print("2) 중앙 채움 스윕 (rev-light 시뮬레이션, 0->100%)")
        for q in range(1, 6):
            led.write_frame(led.frame_for_ratio(q / 5, mode="center"))
            time.sleep(0.5)

        print("3) 레드라인 블링크 5회")
        for _ in range(5):
            led.write_frame(led.frame_for_ratio(1.0, blink_off=True))
            time.sleep(0.12)
            led.write_frame(led.frame_for_ratio(1.0, blink_off=False))
            time.sleep(0.12)

        print("4) 좌->우 채움 스윕")
        for q in range(0, 11):
            led.write_frame(led.frame_for_ratio(q / 10, mode="ltr"))
            time.sleep(0.3)

    finally:
        print("기존 설정 복원...")
        led.restore()
        print("완료. (G HUB 패턴이 안 돌아오면 G HUB에서 프로필 토글)")


if __name__ == "__main__":
    main()
