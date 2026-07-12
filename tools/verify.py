"""하드웨어 검증 스위트 — 게임 없이 휠 연결만으로 전 계층 점검.

usage: python tools/verify.py [--visual]   (--visual: LED 스윕 육안 확인 포함)
"""
import socket
import sys
import time
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import hid

RESULTS = []


def check(name, fn):
    try:
        detail = fn()
        RESULTS.append((name, True, detail or ""))
        print(f"  [PASS] {name}" + (f" — {detail}" if detail else ""))
    except Exception as e:
        RESULTS.append((name, False, str(e)))
        print(f"  [FAIL] {name} — {e}")


def main():
    visual = "--visual" in sys.argv
    print("=== RS50 x FH6 검증 스위트 ===\n")

    # 1. 설정
    def c_config():
        with open(ROOT / "config.toml", "rb") as f:
            cfg = tomllib.load(f)
        for sect in ("telemetry", "shift_keys", "paddles", "override", "auto", "led"):
            assert sect in cfg, f"[{sect}] 섹션 없음"
        assert cfg["paddles"].get("byte_up") is not None, "패들 미설정"
        return f"섹션 {len(cfg)}개"
    check("config.toml 파싱/필수 키", c_config)

    # 2. HID 인터페이스
    def c_hid():
        devs = hid.enumerate(0x046D, 0xC276)
        assert devs, "RS50(046d:c276) 미발견 — 휠 연결/전원 확인"
        pages = {(d.get("usage_page"), d.get("usage")) for d in devs}
        for need in ((0x0001, 0x04), (0xFF43, 0x701), (0xFF43, 0x704)):
            assert need in pages, f"인터페이스 {need} 없음"
        return f"{len(devs)}개 인터페이스"
    check("RS50 HID 인터페이스 열거", c_hid)

    # 3. HID++ 트랜스포트 + feature 인덱스
    from src.hidpp import Rs50Hidpp
    dev = None

    def c_hidpp():
        nonlocal dev
        dev = Rs50Hidpp()
        idx_a = dev.feature_index(0x807A)
        idx_b = dev.feature_index(0x807B)
        idx_p = dev.feature_index(0x8137)
        return f"0x807A@{idx_a} 0x807B@{idx_b} 0x8137@{idx_p}"
    check("HID++ 왕복 (IRoot feature 조회)", c_hidpp)

    def c_name():
        idx = dev.feature_index(0x0005)
        n = dev.call(idx, 0)[0]
        raw = b""
        off = 0
        while off < n:
            raw += dev.call(idx, 1, bytes([off]))
            off = len(raw)
        name = raw[:n].decode(errors="replace")
        assert "RS50" in name, f"예상외 장치명: {name}"
        return name
    check("장치 식별 (DeviceTypeName)", c_name)

    def c_profile():
        idx = dev.feature_index(0x8137)
        p = dev.call(idx, 1)
        return f"profile={p[0]} ({'desktop' if p[0] == 0 else f'onboard {p[0]}'})"
    check("프로필 상태 읽기", c_profile)

    # 4. LED 파이프라인 (읽기 -> 쓰기 -> 되읽기 -> 복원)
    from src.ledctl import Rs50Led

    def c_led():
        led = Rs50Led(dev=dev, slot=0, min_interval=0.0, preset="f1")
        _, b5, orig = led.read_slot(0)
        led.direction = b5
        test = [(1, 2, 3)] * 10
        led.write_fast(test)
        _, _, back = led.read_slot(0)
        assert back == test, f"되읽기 불일치: {back[:3]}..."
        if visual:
            print("      (휠 확인: 3초간 F1 스윕)")
            for q in list(range(0, 11)) + [10]:
                led.write_fast(led.frame_for_ratio(q / 10, mode="ltr"))
                time.sleep(0.25)
        led.write_frame(orig, direction=b5)  # 원본 복원 (풀 시퀀스)
        _, _, back2 = led.read_slot(0)
        assert back2 == orig, "복원 실패"
        return f"쓰기/되읽기/복원 OK (b5={b5})"
    check("LED 슬롯0 쓰기 파이프라인", c_led)

    # 5. 조이스틱(패들) 인터페이스
    def c_joy():
        for d in hid.enumerate(0x046D, 0xC276):
            if d.get("usage_page") == 0x0001 and d.get("usage") == 0x04:
                h = hid.device()
                h.open_path(d["path"])
                h.set_nonblocking(True)
                got = False
                t0 = time.time()
                while time.time() - t0 < 1.0:
                    if h.read(64):
                        got = True
                        break
                    time.sleep(0.005)
                h.close()
                return "리포트 수신 OK" if got else "오픈 OK (입력 이벤트 없음 — 정상)"
        raise AssertionError("조이스틱 인터페이스 없음")
    check("패들 관찰 인터페이스", c_joy)

    # 6. 텔레메트리 포트
    def c_udp():
        with open(ROOT / "config.toml", "rb") as f:
            port = tomllib.load(f)["telemetry"]["port"]
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(("127.0.0.1", port))
        s.close()
        return f"UDP {port} 바인드 가능"
    check("텔레메트리 포트", c_udp)

    # 7. 모듈 임포트 (전체)
    def c_imports():
        import src.main, src.webui, src.autoshift, src.shifter  # noqa
        import src.telemetry, src.paddle_watch  # noqa
        return "src/* 전체"
    check("모듈 임포트", c_imports)

    # 8. 키 인젝션 준비 (실제 키는 안 누름)
    def c_keys():
        import pydirectinput
        assert hasattr(pydirectinput, "keyDown")
        return "pydirectinput OK"
    check("키 인젝션 라이브러리", c_keys)

    if dev:
        dev.close()

    fails = [r for r in RESULTS if not r[1]]
    print(f"\n결과: {len(RESULTS) - len(fails)}/{len(RESULTS)} PASS"
          + (f" — 실패: {[r[0] for r in fails]}" if fails else " — 전 항목 통과"))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
