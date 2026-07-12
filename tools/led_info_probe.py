"""LED 후보 feature 읽기 전용 정보 프로브.

0x8040(BrightnessControl), 0x807A, 0x807B 의 func 0(관례상 getInfo/getCaps)만
호출해 raw 응답을 덤프한다. set 계열은 호출하지 않는다.

usage: python tools/led_info_probe.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.hidpp import Rs50Hidpp, HidppError

TARGETS = [0x8040, 0x807A, 0x807B]


def hexdump(b):
    return " ".join(f"{x:02x}" for x in b)


def main():
    dev = Rs50Hidpp()
    for feat in TARGETS:
        try:
            idx = dev.feature_index(feat)
        except Exception as e:
            print(f"0x{feat:04X}: index 조회 실패 ({e})")
            continue
        print(f"\n=== feature 0x{feat:04X} (idx {idx}) ===")
        for func in (0, 1):  # 0=getInfo(관례), 1도 대부분 getter — 그 이상은 호출 안 함
            try:
                p = dev.call(idx, func)
                print(f"  func {func}: {hexdump(p)}")
            except HidppError as e:
                print(f"  func {func}: HID++ err {e.code} "
                      f"({'INVALID_FUNCTION_ID' if e.code == 7 else ''})")
            except TimeoutError:
                print(f"  func {func}: timeout")
    dev.close()


if __name__ == "__main__":
    main()
