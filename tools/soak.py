"""소크 테스트 — 실전 시나리오를 장시간 주입하며 앱 안정성 검증.

앱을 서브프로세스로 띄우고, 텔레메트리 사이클(발진/변속/코스트/정차/메뉴/차량교체/
쓰레기 패킷)을 반복 송신. 종료 후 로그에서 오류율·HB 연속성·메모리 추이를 리포트.

usage: python tools/soak.py [분(기본 30)]
주의: 포커스 가드 덕에 키 인젝션은 게임 창이 없으면 발생하지 않음 (안전).
"""
import re
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "soak_run.log"
with open(ROOT / "config.toml", "rb") as _f:
    PORT = tomllib.load(_f)["telemetry"]["port"]
GARBAGE_SIZES = (10, 100, 500)


def pkt(rpm, max_rpm=8000.0, gear=3, speed=30.0, accel=0, size=324):
    b = bytearray(size)
    struct.pack_into("<i", b, 0, 1)
    struct.pack_into("<f", b, 8, max_rpm)
    struct.pack_into("<f", b, 12, 800.0)
    struct.pack_into("<f", b, 16, rpm)
    if size == 324:
        struct.pack_into("<f", b, 256, speed)
        b[315] = accel
        b[319] = gear
    return bytes(b)


def drive_cycle(sock, max_rpm):
    """1사이클 ≈ 75초: 발진->6단까지 가속->코스트 다운->정차->메뉴 10초."""
    idle = 800.0
    # 가속: 기어 1->6, 각 기어에서 rpm 50%->95% 스윕
    for gear in range(1, 7):
        r = 0.5
        while r < 0.95:
            sock.sendto(pkt(idle + r * (max_rpm - idle), max_rpm, gear,
                            speed=10.0 * gear, accel=255), ("127.0.0.1", PORT))
            r += 0.03
            time.sleep(1 / 60)
    # 코스트 다운: 기어 6->1, rpm 하강
    for gear in range(6, 0, -1):
        r = 0.6
        while r > 0.25:
            sock.sendto(pkt(idle + r * (max_rpm - idle), max_rpm, gear,
                            speed=8.0 * gear, accel=0), ("127.0.0.1", PORT))
            r -= 0.04
            time.sleep(1 / 60)
    # 정차 5초 (아이들)
    t0 = time.time()
    while time.time() - t0 < 5:
        sock.sendto(pkt(idle + 50, max_rpm, 1, speed=0.0), ("127.0.0.1", PORT))
        time.sleep(1 / 60)
    # 쓰레기 패킷 몇 발 (무해해야 함 — 크기별 경고 1회씩만 나와야 함)
    for n in GARBAGE_SIZES:
        sock.sendto(b"\xff" * n, ("127.0.0.1", PORT))
    # 메뉴: 10초 침묵
    time.sleep(10)


def mem_mb(pid):
    r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                       capture_output=True, text=True)
    try:
        return int(r.stdout.split('","')[-1].strip('" K\n').replace(",", "")) / 1024
    except (ValueError, IndexError):
        return -1


def main():
    minutes = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
    print(f"소크 {minutes:.0f}분 시작")
    app = subprocess.Popen(
        [sys.executable, "-m", "src.main", "--led"],
        cwd=ROOT, stdout=open(LOG, "w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        env={**__import__("os").environ,
             "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"})
    time.sleep(4)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    t_end = time.time() + minutes * 60
    cycle = 0
    mems = [mem_mb(app.pid)]
    car = [8000.0, 6500.0, 12000.0]
    try:
        while time.time() < t_end:
            drive_cycle(sock, car[cycle % len(car)])  # 사이클마다 차량 교체
            cycle += 1
            mems.append(mem_mb(app.pid))
            if app.poll() is not None:
                print(f"!! 앱이 죽음 (사이클 {cycle}, 코드 {app.returncode})")
                break
            print(f"  사이클 {cycle} 완료, mem {mems[-1]:.0f}MB", flush=True)
    finally:
        alive = app.poll() is None
        if alive:
            app.terminate()
            time.sleep(1)
            if app.poll() is None:
                app.kill()

    text = LOG.read_text(encoding="utf-8", errors="replace")
    led_err = len(re.findall(r"\[LED\] 오류", text))
    fsm_err = len(re.findall(r"\[FSM\] 오류", text))
    tracebacks = len(re.findall(r"Traceback", text))
    hbs = len(re.findall(r"\[HB\]", text))
    unknown = len(re.findall(r"알 수 없는 패킷", text))
    shifts = len(re.findall(r"\[AUTO\]", text))
    growth = mems[-1] - mems[0] if mems[0] > 0 and mems[-1] > 0 else float("nan")

    print("\n===== 소크 리포트 =====")
    print(f"사이클 {cycle}회 / 앱 생존: {alive}")
    print(f"LED 오류 {led_err} / FSM 오류 {fsm_err} / Traceback {tracebacks}")
    skips = len(re.findall(r"인젝션 보류", text))
    print(f"HB {hbs}회 / 미지 패킷 경고 {unknown} (크기 종류 {len(GARBAGE_SIZES)}개 = 정상) "
          f"/ AUTO 로그 {shifts} / 인젝션 보류 로그 {skips}")
    print(f"메모리 {mems[0]:.0f} -> {mems[-1]:.0f}MB (증가 {growth:+.0f}MB)")
    telem_ok = len(re.findall(r"telem=OK", text))
    ok = alive and tracebacks == 0 and unknown <= len(GARBAGE_SIZES) \
        and telem_ok > 0 and (math_isnan(growth) or growth < 50)
    if telem_ok == 0:
        print("!! telem=OK 0회 — 텔레메트리가 앱에 도달하지 않음 (포트 확인)")
    print("판정:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


def math_isnan(x):
    return x != x


if __name__ == "__main__":
    main()
