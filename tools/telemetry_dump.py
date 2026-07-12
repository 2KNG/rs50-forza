"""라이브 텔레메트리 확인 도구.

게임에서 Data Out 켠 뒤 실행 — 패킷 크기와 rpm/gear 등이 실차와 맞는지 검증.

usage: python tools/telemetry_dump.py [port]
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.telemetry import TelemetryListener, TelemetryState


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5607
    state = TelemetryState()
    TelemetryListener(port, state).start()
    print(f"UDP {port} 수신 대기... (Ctrl+C 종료)")
    while True:
        time.sleep(0.25)
        if state.last_rx == 0:
            continue
        print(f"pkt={state.packet_size}B race={state.is_race_on} "
              f"rpm={state.rpm:6.0f}/{state.max_rpm:6.0f} (idle {state.idle_rpm:5.0f}) "
              f"ratio={state.rpm_ratio:4.2f} gear={state.gear} "
              f"spd={state.speed*3.6:5.1f}km/h acc={state.accel:3d} brk={state.brake:3d}",
              end="\r")


if __name__ == "__main__":
    main()
