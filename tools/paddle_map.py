"""패들 (byte, bit) 위치 실측 도구.

실행 후 안내에 따라 패들을 당기면, 입력 리포트에서 변한 byte/bit를 보여준다.
결과를 config.toml [paddles] 에 기입할 것.

usage: python tools/paddle_map.py
"""
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


def snapshot(h, dur=0.6):
    """dur 동안 리포트를 모아 마지막 상태 반환."""
    last = None
    t0 = time.time()
    while time.time() - t0 < dur:
        data = bytes(h.read(64))
        if data:
            last = data
        time.sleep(0.002)
    return last


def diff_bits(base, cur):
    out = []
    for i, (a, b) in enumerate(zip(base, cur)):
        x = a ^ b
        for bit in range(8):
            if x & (1 << bit):
                out.append((i, bit, bool(b & (1 << bit))))
    return out


def capture(h, label):
    input(f"\n[{label}] 아무것도 만지지 말고 Enter...")
    base = snapshot(h)
    input(f"[{label}] 이제 해당 패들을 꾹 잡은 채로 Enter...")
    cur = snapshot(h)
    if not base or not cur:
        print("  리포트 수신 실패 — 휠이 절전 상태인지 확인")
        return
    changes = diff_bits(base, cur)
    # 축 노이즈(연속값) 제거를 위해 set(1)된 비트 위주로 표시
    print(f"  변화 비트: {[(f'byte {i}', f'bit {b}', 'ON' if v else 'off') for i, b, v in changes]}")
    on = [(i, b) for i, b, v in changes if v]
    if len(on) == 1:
        print(f"  => config.toml: byte={on[0][0]}, bit={on[0][1]}")
    elif on:
        print("  => 후보가 여럿 — 스티어링/페달 건드리지 말고 재시도 권장")


def main():
    h = open_joystick()
    print("RS50 패들 매핑 시작. 스티어링/페달은 건드리지 마세요.")
    capture(h, "오른쪽 패들 (시프트 업)")
    capture(h, "왼쪽 패들 (시프트 다운)")
    h.close()


if __name__ == "__main__":
    main()
