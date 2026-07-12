"""RS50 HID 인터페이스 열거 + 병렬 오픈 실험.

G HUB가 실행 중인 상태에서 파이썬(hidapi)이 RS50의 각 HID 인터페이스를
열 수 있는지, 입력 리포트를 읽을 수 있는지 확인한다.

usage:
    python tools/hid_enum.py           # 열거 + 오픈 테스트만
    python tools/hid_enum.py --watch   # 열리는 인터페이스에서 5초간 입력 리포트 관찰
                                       # (실행 중 패들을 당겨볼 것)
"""
import sys
import time

import hid

VID = 0x046D
PID_RS50 = 0xC276  # 이 PC에서 확인된 RS50 PID (compat 모드 아님, G HUB 네이티브)


def enumerate_rs50():
    devs = [d for d in hid.enumerate(VID) if d["product_id"] == PID_RS50]
    if not devs:
        print(f"RS50({VID:04x}:{PID_RS50:04x}) 미발견. 연결된 Logitech 장치:")
        for d in hid.enumerate(VID):
            print(f"  {d['vendor_id']:04x}:{d['product_id']:04x} {d.get('product_string','?')}")
        sys.exit(1)
    return devs


def try_open(dev_info):
    h = hid.device()
    try:
        h.open_path(dev_info["path"])
        return h, None
    except OSError as e:
        return None, str(e)


def main(watch=False):
    devs = enumerate_rs50()
    print(f"RS50 HID 인터페이스 {len(devs)}개 발견:\n")
    opened = []
    for d in devs:
        up, u = d.get("usage_page", 0), d.get("usage", 0)
        iface = d.get("interface_number", -1)
        h, err = try_open(d)
        status = "OPEN OK" if h else f"OPEN FAIL: {err}"
        print(f"  iface={iface:>2}  usage_page=0x{up:04X} usage=0x{u:02X}  "
              f"path={d['path'].decode(errors='replace')}")
        print(f"           -> {status}")
        if h:
            opened.append((d, h))

    if not watch:
        for _, h in opened:
            h.close()
        print(f"\n결과: {len(opened)}/{len(devs)} 인터페이스 오픈 성공 (G HUB 실행 중)")
        return

    print("\n--- 5초간 입력 리포트 관찰 (지금 패들/버튼을 조작하세요) ---")
    for _, h in opened:
        h.set_nonblocking(True)
    t0 = time.time()
    counts = {}
    samples = {}
    while time.time() - t0 < 5.0:
        for d, h in opened:
            data = h.read(64)
            if data:
                key = d.get("interface_number", -1), d.get("usage_page", 0)
                counts[key] = counts.get(key, 0) + 1
                # 리포트 내용이 바뀔 때만 저장 (최대 6개)
                sl = samples.setdefault(key, [])
                if len(sl) < 6 and (not sl or sl[-1] != data):
                    sl.append(data)
        time.sleep(0.001)
    print()
    for key, n in counts.items():
        iface, up = key
        print(f"iface={iface} usage_page=0x{up:04X}: {n}개 리포트 수신")
        for s in samples.get(key, []):
            print("   ", " ".join(f"{b:02x}" for b in s[:32]))
    if not counts:
        print("수신된 리포트 없음 — 읽기는 되지만 이벤트가 없거나, G HUB가 입력을 독점 중일 수 있음")
    for _, h in opened:
        h.close()


if __name__ == "__main__":
    main(watch="--watch" in sys.argv)
