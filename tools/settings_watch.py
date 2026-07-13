"""휠 설정 변경 브로드캐스트 감시 (읽기 전용, 안전).

휠은 설정이 바뀔 때마다 SW_ID=0 브로드캐스트를 쏨 (OLED 조작, G HUB 재적용,
펌웨어 자체 변경 포함). 이 도구는 그걸 실시간 디코드 — "누가 내 설정을
바꿨나"를 잡는 용도.

usage: python tools/settings_watch.py [초(기본 60)]
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import hid

VID, PID = 0x046D, 0xC276

IDX_NAMES = {
    0x08: "topology", 0x0B: "LED effect", 0x0C: "LED RGB", 0x0A: "brightness",
    0x14: "댐핑", 0x15: "브레이크포스", 0x16: "FFB강도", 0x17: "프로필",
    0x18: "회전범위", 0x19: "TRUEFORCE", 0x1A: "FFB필터",
}


def be16(b, i):
    return (b[i] << 8) | b[i + 1] if len(b) > i + 1 else -1


def decode(b):
    idx = b[2]
    name = IDX_NAMES.get(idx, f"idx {idx:#04x}")
    val = be16(b, 4)
    extra = ""
    if idx == 0x17:
        extra = f" -> profile {b[4]}"
    elif idx == 0x18:
        extra = f" -> {val}°"
    elif idx == 0x16:
        extra = f" -> {val/8192:.1f}Nm"
    elif idx in (0x14, 0x15, 0x19):
        extra = f" -> {val/655.35:.0f}%"
    return f"[{name}]{extra}  raw {' '.join(f'{x:02x}' for x in b[:10])}"


def main():
    dur = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0
    handles = []
    for d in hid.enumerate(VID, PID):
        if d.get("usage_page") == 0xFF43 and d.get("usage") in (0x702, 0x704):
            h = hid.device()
            h.open_path(d["path"])
            h.set_nonblocking(True)
            handles.append(h)
    print(f"{dur:.0f}초 감시 시작 (설정을 바꾸면 여기 찍힘 — OLED/G HUB 조작해보세요)")
    t0 = time.time()
    n = 0
    while time.time() - t0 < dur:
        for h in handles:
            b = bytes(h.read(64))
            if len(b) >= 5 and b[1] == 0xFF and (b[3] & 0x0F) == 0:
                n += 1
                print(f"  [{time.time()-t0:6.1f}s] {decode(b)}", flush=True)
        time.sleep(0.005)
    print(f"종료 — 브로드캐스트 {n}건")
    for h in handles:
        h.close()


if __name__ == "__main__":
    main()
