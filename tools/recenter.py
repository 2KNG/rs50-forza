"""RS50 센터 캘리브레이션 — 우측 쏠림 해결 도구.

프로토콜 (mescon 스펙, 실측 검증): 캘리브레이션 = 서브디바이스 0x05의
feature 0x812C. fn1 GET = 라이브 엔코더 원시값(BE u16), fn3 SET = 그 절대값을
센터로 채택 (펌웨어에 영구 저장).

usage:
    python tools/recenter.py           # 현재 엔코더 값 읽기 + 드리프트 리포트
    python tools/recenter.py --set     # [휠을 정중앙으로 잡은 상태에서] 센터 저장
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.hidpp import Rs50Hidpp

STORE = ROOT / "center_calibration.json"
DEV_MOTOR = 0x05
FEAT_CAL = 0x812C


def get_cal_index(dev):
    p = dev.call(0x00, 0, bytes([FEAT_CAL >> 8, FEAT_CAL & 0xFF]),
                 dev_idx=DEV_MOTOR)
    idx = p[0]
    if idx == 0:
        raise RuntimeError("0x812C 미지원 (서브디바이스 0x05)")
    return idx


def read_raw(dev, idx):
    p = dev.call(idx, 1, dev_idx=DEV_MOTOR)
    return (p[0] << 8) | p[1]


def stillness_check(dev, idx):
    a = read_raw(dev, idx)
    time.sleep(0.05)
    b = read_raw(dev, idx)
    return abs(a - b) <= 200, a, b


def main():
    dev = Rs50Hidpp()
    idx = get_cal_index(dev)
    print(f"0x812C @ dev 0x05 idx {idx}")

    still, a, b = stillness_check(dev, idx)
    print(f"엔코더 원시값: {a} -> {b} (Δ{abs(a-b)}, {'정지' if still else '움직임 감지'})")

    saved = None
    if STORE.exists():
        saved = json.loads(STORE.read_text())["center_raw"]
        print(f"저장된 센터값: {saved} (드리프트 {a - saved:+d} counts)")
    else:
        print("저장된 센터값 없음 — --set으로 최초 저장 필요")

    if "--set" in sys.argv:
        if not still:
            print("!! 휠이 움직이는 중 — 정중앙으로 잡고 다시 실행")
            sys.exit(1)
        input(f"휠이 정확히 정중앙입니까? Enter = 센터를 {b}로 저장 (Ctrl+C 취소) ")
        dev.call(idx, 3, bytes([b >> 8, b & 0xFF, 0]), dev_idx=DEV_MOTOR)
        STORE.write_text(json.dumps({"center_raw": b, "ts": time.time()}))
        print(f"센터 저장 완료: {b} (펌웨어 영구 저장)")
        # 검증: 조이스틱 인터페이스 스티어링 축이 0x8000 근처인지
        import hid
        for d in hid.enumerate(0x046D, 0xC276):
            if d.get("usage_page") == 0x0001 and d.get("usage") == 0x04:
                h = hid.device(); h.open_path(d["path"]); h.set_nonblocking(True)
                time.sleep(0.2)
                data = bytes(h.read(64)) or bytes(h.read(64))
                h.close()
                if len(data) >= 6:
                    axis = data[4] | (data[5] << 8)
                    print(f"조이스틱 스티어링 축: {axis:#06x} "
                          f"(0x8000 근처면 정상, 오차 {abs(axis-0x8000)})")
                break
    dev.close()


if __name__ == "__main__":
    main()
