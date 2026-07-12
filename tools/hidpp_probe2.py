"""RS50 HID++ 채널 진단 v2.

1) 0xFF43 컬렉션 3개 + 0xFFFD 인터페이스를 전부 열고 3초간 패시브 관찰
   (G HUB <-> 장치 간 오가는 리포트 ID 파악)
2) (핸들 x 리포트ID(0x10/0x11/0x12) x devIdx(0xFF/0x00)) 조합으로
   IRoot.getFeature(0x0001) 전송, 모든 핸들에서 응답 수집

usage: python tools/hidpp_probe2.py
"""
import time

import hid

VID, PID = 0x046D, 0xC276
SW_ID = 0x0A

SIZES = {0x10: 7, 0x11: 20, 0x12: 64}


def open_all():
    handles = []
    for d in hid.enumerate(VID, PID):
        up = d.get("usage_page", 0)
        if up not in (0xFF43, 0xFFFD):
            continue
        h = hid.device()
        try:
            h.open_path(d["path"])
            h.set_nonblocking(True)
            handles.append((f"up={up:04X}/u={d.get('usage',0):03X}", h))
        except OSError as e:
            print(f"  open fail up={up:04X}/u={d.get('usage',0):03X}: {e}")
    return handles


def drain(handles, dur, label):
    seen = []
    t0 = time.time()
    while time.time() - t0 < dur:
        for name, h in handles:
            data = bytes(h.read(64))
            if data:
                seen.append((name, data))
        time.sleep(0.001)
    if seen:
        print(f"[{label}] 수신 {len(seen)}건:")
        uniq = {}
        for name, data in seen:
            key = (name, data[:8])
            uniq.setdefault(key, [0, data])[0] += 1
        for (name, _), (n, data) in list(uniq.items())[:20]:
            print(f"   {name}  x{n}  {' '.join(f'{b:02x}' for b in data[:24])}")
    else:
        print(f"[{label}] 수신 없음")
    return seen


def main():
    handles = open_all()
    print(f"오픈된 핸들 {len(handles)}개: {[n for n, _ in handles]}\n")

    print("--- 패시브 관찰 3초 (G HUB 트래픽) ---")
    drain(handles, 3.0, "passive")

    print("\n--- 액티브 프로브: IRoot.getFeature(0x0001) ---")
    for name, h in handles:
        for rid, size in SIZES.items():
            for devidx in (0xFF, 0x00):
                func_sw = (0 << 4) | SW_ID
                req = bytes([rid, devidx, 0x00, func_sw, 0x00, 0x01])
                req = req + b"\x00" * (size - len(req))
                try:
                    n = h.write(req)
                except OSError as e:
                    print(f"  {name} rid=0x{rid:02X} dev=0x{devidx:02X}: write err ({e})")
                    continue
                if n <= 0:
                    print(f"  {name} rid=0x{rid:02X} dev=0x{devidx:02X}: write ret {n}")
                    continue
                print(f"  {name} rid=0x{rid:02X} dev=0x{devidx:02X}: wrote {n}B, 응답 대기...")
                resp = drain(handles, 0.8, f"resp {name} rid={rid:02X} dev={devidx:02X}")
                if resp:
                    return  # 응답 나오는 조합 발견 시 중단 (수동 분석)

    for _, h in handles:
        h.close()


if __name__ == "__main__":
    main()
