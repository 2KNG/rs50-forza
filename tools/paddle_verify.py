"""config.toml의 패들 매핑 라이브 검증 — 30초간 눌림 이벤트를 실시간 판정.

usage: python tools/paddle_verify.py
"""
import sys
import time
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.paddle_capture import open_joystick


def main():
    root = Path(__file__).resolve().parent.parent
    with open(root / "config.toml", "rb") as f:
        p = tomllib.load(f)["paddles"]
    bu, iu, bd, idn = p["byte_up"], p["bit_up"], p["byte_down"], p["bit_down"]
    print(f"매핑: UP=byte{bu}.bit{iu}  DOWN=byte{bd}.bit{idn} — 30초간 패들을 눌러보세요",
          flush=True)

    h = open_joystick()
    prev_u = prev_d = False
    n_u = n_d = 0
    t0 = time.time()
    while time.time() - t0 < 30:
        data = bytes(h.read(64))
        if not data or len(data) <= max(bu, bd):
            time.sleep(0.001)
            continue
        u = bool(data[bu] & (1 << iu))
        d = bool(data[bd] & (1 << idn))
        if u and not prev_u:
            n_u += 1
            print(f"  [{time.time()-t0:5.1f}s] 오른쪽 패들(UP) 눌림 #{n_u}", flush=True)
        if d and not prev_d:
            n_d += 1
            print(f"  [{time.time()-t0:5.1f}s] 왼쪽 패들(DOWN) 눌림 #{n_d}", flush=True)
        prev_u, prev_d = u, d
    h.close()
    print(f"\n결과: UP {n_u}회 / DOWN {n_d}회 감지")


if __name__ == "__main__":
    main()
