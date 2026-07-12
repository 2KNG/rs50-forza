"""패들 비트 자동 실측 — 90초간 조이스틱 리포트의 비트 전이를 기록/분석.

사용자는 캡처 중: 오른쪽 패들 3회 -> (3초 이상 대기) -> 왼쪽 패들 3회.
분석: 깨끗한 버스트 전이를 보이는 비트를 후보로, 시간순으로 R/L 판별.

usage: python tools/paddle_capture.py [duration_s]
"""
import sys
import time

import hid

VID, PID = 0x046D, 0xC276


def open_joystick():
    for d in hid.enumerate(VID, PID):
        if d.get("usage_page") == 0x0001 and d.get("usage") == 0x04:
            h = hid.device()
            h.open_path(d["path"])
            h.set_nonblocking(True)
            return h
    raise SystemExit("RS50 조이스틱 인터페이스 미발견")


def main():
    dur = float(sys.argv[1]) if len(sys.argv) > 1 else 90.0
    h = open_joystick()
    print(f"{dur:.0f}초 캡처 시작", flush=True)

    prev = None
    events = {}  # (byte,bit) -> [(t, newval), ...]
    t0 = time.time()
    n_reports = 0
    while time.time() - t0 < dur:
        data = bytes(h.read(64))
        if not data:
            time.sleep(0.001)
            continue
        n_reports += 1
        if prev is not None and len(data) == len(prev):
            for i, (a, b) in enumerate(zip(prev, data)):
                x = a ^ b
                if not x:
                    continue
                for bit in range(8):
                    if x & (1 << bit):
                        events.setdefault((i, bit), []).append(
                            (time.time() - t0, bool(b & (1 << bit))))
        prev = data
    h.close()

    print(f"\n리포트 {n_reports}개 수신, 변화 비트 {len(events)}종")
    if not events:
        print("변화 없음 — 캡처 중 패들 입력이 없었던 것 같음")
        return

    # 후보 필터: 2~40회 전이(버스트), 노이즈(상시 변동) 제외
    cands = []
    for (byte, bit), evs in sorted(events.items()):
        presses = sum(1 for _, v in evs if v)
        first_t = evs[0][0]
        last_t = evs[-1][0]
        noisy = len(evs) > 40 or (last_t - first_t) > dur * 0.85 and len(evs) > 20
        mark = "노이즈" if noisy else f"후보 (눌림 {presses}회)"
        print(f"  byte {byte:2d} bit {bit}: 전이 {len(evs):3d}회, "
              f"{first_t:5.1f}s~{last_t:5.1f}s  {mark}")
        if not noisy and 2 <= presses <= 20:
            cands.append((first_t, byte, bit, presses))

    cands.sort()
    print()
    if len(cands) >= 2:
        r, l = cands[0], cands[1]
        print("판정 (먼저 누른 쪽 = 오른쪽/업):")
        print(f"  [paddles]")
        print(f"  byte_up = {r[1]}")
        print(f"  bit_up = {r[2]}")
        print(f"  byte_down = {l[1]}")
        print(f"  bit_down = {l[2]}")
    elif len(cands) == 1:
        print(f"후보 1개만 검출: byte {cands[0][1]} bit {cands[0][2]} — 한쪽만 눌렀는지?")
    else:
        print("깨끗한 후보 없음 — 재캡처 필요")


if __name__ == "__main__":
    main()
