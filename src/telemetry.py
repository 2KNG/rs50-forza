"""Forza Data Out UDP 텔레메트리 수신/파싱.

패킷 크기로 포맷을 자동 판별한다:
  232B = Sled, 311B = Motorsport Dash, 324B = Horizon(FH4/FH5) Dash
FH6 포맷은 리서치 확정 후 필요 시 테이블 추가/수정.
[주의] 324B 테이블의 dash 구간 오프셋은 커뮤니티 문서 기반 —
tools/telemetry_dump.py 로 실차 값과 대조해 검증할 것.
"""
import socket
import struct
import threading
import time

# 공통(sled 구간, 모든 포맷 동일)
_SLED = {
    "is_race_on":  (0,   "<i"),
    "timestamp_ms": (4,  "<I"),
    "max_rpm":     (8,   "<f"),
    "idle_rpm":    (12,  "<f"),
    "rpm":         (16,  "<f"),
}

# 패킷 크기별 dash 구간 오프셋
_DASH_TABLES = {
    311: {  # Motorsport dash
        "speed": (244, "<f"), "power": (248, "<f"), "torque": (252, "<f"),
        "accel": (303, "<B"), "brake": (304, "<B"), "clutch": (305, "<B"),
        "handbrake": (306, "<B"), "gear": (307, "<B"), "steer": (308, "<b"),
    },
    324: {  # Horizon (FH4/FH5): sled 뒤에 12B unknown 삽입 -> dash 구간 +12
        "speed": (256, "<f"), "power": (260, "<f"), "torque": (264, "<f"),
        "accel": (315, "<B"), "brake": (316, "<B"), "clutch": (317, "<B"),
        "handbrake": (318, "<B"), "gear": (319, "<B"), "steer": (320, "<b"),
    },
}


class TelemetryState:
    """최신 텔레메트리 스냅샷 (스레드 안전은 GIL + 단순 대입에 의존)."""
    def __init__(self):
        self.packet_size = 0
        self.last_rx = 0.0
        self.is_race_on = 0
        self.max_rpm = 0.0
        self.idle_rpm = 0.0
        self.rpm = 0.0
        self.speed = 0.0
        self.power = 0.0
        self.torque = 0.0
        self.accel = 0
        self.brake = 0
        self.clutch = 0
        self.handbrake = 0
        self.gear = 0
        self.steer = 0

    @property
    def alive(self):
        """차량 탑승 중 판정: is_race_on 대신 max_rpm>0 && 최근 수신."""
        return self.max_rpm > 0 and (time.time() - self.last_rx) < 0.5

    @property
    def rpm_ratio(self):
        if self.max_rpm <= self.idle_rpm:
            return 0.0
        return max(0.0, (self.rpm - self.idle_rpm) / (self.max_rpm - self.idle_rpm))


class TelemetryListener(threading.Thread):
    def __init__(self, port, state: TelemetryState):
        super().__init__(daemon=True, name="telemetry")
        self.port = port
        self.state = state
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", self.port))
        sock.settimeout(0.5)
        s = self.state
        while not self._stop.is_set():
            try:
                data, _ = sock.recvfrom(1024)
            except socket.timeout:
                continue
            n = len(data)
            fields = dict(_SLED)
            fields.update(_DASH_TABLES.get(n, {}))
            for name, (off, fmt) in fields.items():
                if off + struct.calcsize(fmt) <= n:
                    setattr(s, {"is_race_on": "is_race_on"}.get(name, name),
                            struct.unpack_from(fmt, data, off)[0])
            s.packet_size = n
            s.last_rx = time.time()
        sock.close()
