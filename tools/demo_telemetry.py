"""데모 텔레메트리 — 게임 없이 대시보드 개발/시연용 드리프트 시뮬레이션.

발진 -> 가속 -> 드리프트 진입(핸드브레이크) -> 각 유지 -> 복귀를 반복하는
합성 324B 패킷을 60Hz로 송신. 타이어 슬립/온도/서스까지 그럴싸하게 생성.

usage: python tools/demo_telemetry.py [분(기본 10)]
"""
import math
import socket
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import tomllib

with open(ROOT / "config.toml", "rb") as f:
    PORT = tomllib.load(f)["telemetry"]["port"]

IDLE, MAX = 900.0, 8500.0


def pkt(t):
    """시각 t(초) 기준 드리프트 사이클 합성 (사이클 20초)."""
    c = t % 20.0
    b = bytearray(324)
    struct.pack_into("<i", b, 0, 1)
    struct.pack_into("<f", b, 8, MAX)
    struct.pack_into("<f", b, 12, IDLE)

    if c < 4:            # 가속
        ratio = 0.5 + c / 4 * 0.45
        drift = 0.0
        speed = 15 + c * 10
        gear, accel, brake, hb, steer = 3, 255, 0, 0, 10
    elif c < 6:          # 진입 (핸드브레이크 + 카운터)
        k = (c - 4) / 2
        ratio = 0.85
        drift = -35 * math.sin(k * math.pi / 2)
        speed = 55 - k * 10
        gear, accel, brake, hb = 3, 120, 0, 255 if c < 4.6 else 0
        steer = int(90 * k)
    elif c < 14:         # 각 유지 (사인파 흔들림)
        k = c - 6
        ratio = 0.8 + 0.15 * math.sin(k * 2.2)
        drift = -38 + 10 * math.sin(k * 1.7)
        speed = 45 + 5 * math.sin(k)
        gear, accel, brake, hb = 3, 200 + int(50 * math.sin(k * 3)), 0, 0
        steer = int(70 + 25 * math.sin(k * 1.7))
    else:                # 복귀 + 순항
        k = (c - 14) / 6
        ratio = max(0.55, 0.8 - k * 0.3)
        drift = -38 * max(0.0, 1 - k * 2)
        speed = 50 + k * 20
        gear, accel, brake, hb = 4, 180, 0, 0
        steer = int(70 * max(0.0, 1 - k * 2))

    rpm = IDLE + ratio * (MAX - IDLE)
    drift_r = math.radians(drift)
    vz = speed * math.cos(drift_r)
    vx = speed * math.sin(drift_r)
    lat_g = 9.81 * (1.3 * math.sin(drift_r) + 0.2 * math.sin(c * 5))

    struct.pack_into("<f", b, 16, rpm)
    struct.pack_into("<f", b, 20, lat_g)                    # accel_x
    struct.pack_into("<f", b, 28, 3.0 * math.cos(drift_r))  # accel_z
    struct.pack_into("<f", b, 32, vx)
    struct.pack_into("<f", b, 40, vz)
    struct.pack_into("<f", b, 48, math.radians(drift) * 1.5)  # yaw rate

    # 4륜: 드리프트 중 리어 슬립↑, 온도 상승
    base_t = 140 + 60 * min(1.0, abs(drift) / 40)  # F
    for i, w in enumerate(("fl", "fr", "rl", "rr")):
        rear = i >= 2
        slip = abs(drift) / 18 * (1.6 if rear else 0.7) + 0.1
        struct.pack_into("<f", b, 76 + i * 4, slip)             # slip ratio
        struct.pack_into("<f", b, 156 + i * 4, drift_r * (1.2 if rear else 0.5))
        struct.pack_into("<f", b, 172 + i * 4, slip)            # combined
        struct.pack_into("<f", b, 188 + i * 4,
                         0.5 + 0.3 * math.sin(c * 4 + i))       # suspension
        struct.pack_into("<f", b, 268 + i * 4,
                         base_t + (25 if rear else 0) + i * 3)  # temp F

    # 주행 라인: 큰 원 + 드리프트 흔들림
    th = t * 0.25
    struct.pack_into("<f", b, 244, 300 * math.cos(th) + 8 * math.sin(t * 2))
    struct.pack_into("<f", b, 252, 300 * math.sin(th) + 8 * math.cos(t * 1.7))
    struct.pack_into("<i", b, 212, 3296)   # car ordinal (데모)
    struct.pack_into("<i", b, 216, 5)      # S2
    struct.pack_into("<i", b, 220, 998)    # PI
    struct.pack_into("<f", b, 256, speed / 3.6 * 3.6 / 3.6 * 3.6)  # m/s
    struct.pack_into("<f", b, 256, speed)  # m/s (표시부에서 x3.6)
    b[315] = accel
    b[316] = brake
    b[318] = hb
    b[319] = gear
    struct.pack_into("<b", b, 320, max(-127, min(127, steer)))
    return bytes(b)


def main():
    minutes = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"데모 드리프트 텔레메트리 -> UDP {PORT} ({minutes:.0f}분)")
    t0 = time.time()
    while time.time() - t0 < minutes * 60:
        sock.sendto(pkt(time.time() - t0), ("127.0.0.1", PORT))
        time.sleep(1 / 60)


if __name__ == "__main__":
    main()
