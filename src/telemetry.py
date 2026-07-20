"""Forza Data Out UDP 텔레메트리 수신/파싱.

패킷 크기로 포맷을 자동 판별한다:
  232B = Sled, 311B = Motorsport Dash, 324B = Horizon(FH4/FH5/FH6) Dash
알 수 없는 크기는 상태를 오염시키지 않도록 통째로 무시한다(1회 경고).
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
    "accel_x":     (20,  "<f"),  # 로컬 가로 가속 (우+) — 횡G
    "accel_z":     (28,  "<f"),  # 로컬 전방 가속
    "vel_x":       (32,  "<f"),  # 로컬 가로 속도 — 드리프트 각 계산용
    "vel_z":       (40,  "<f"),  # 로컬 전방 속도
    "ang_vel_y":   (48,  "<f"),  # 요 레이트
    "car_ordinal": (212, "<i"),  # 차량 고유 ID (차별 학습/표시용)
    "car_class":   (216, "<i"),  # 0=D..7=X
    "car_pi":      (220, "<i"),  # 퍼포먼스 인덱스
    # 4륜 타이어/서스 (FL, FR, RL, RR)
    "sr_fl": (76, "<f"), "sr_fr": (80, "<f"),   # 슬립비 (구동 슬립)
    "sr_rl": (84, "<f"), "sr_rr": (88, "<f"),
    "sa_fl": (156, "<f"), "sa_fr": (160, "<f"),  # 슬립각
    "sa_rl": (164, "<f"), "sa_rr": (168, "<f"),
    "cs_fl": (172, "<f"), "cs_fr": (176, "<f"),  # 복합 슬립 (1=그립 한계)
    "cs_rl": (180, "<f"), "cs_rr": (184, "<f"),
    "sus_fl": (188, "<f"), "sus_fr": (192, "<f"),  # 서스 트래블 (0~1 정규화)
    "sus_rl": (196, "<f"), "sus_rr": (200, "<f"),
}

# 패킷 크기별 dash 구간 오프셋
_DASH_TABLES = {
    311: {  # Motorsport dash
        "speed": (244, "<f"), "power": (248, "<f"), "torque": (252, "<f"),
        "accel": (303, "<B"), "brake": (304, "<B"), "clutch": (305, "<B"),
        "handbrake": (306, "<B"), "gear": (307, "<B"), "steer": (308, "<b"),
    },
    324: {  # Horizon (FH4/FH5/FH6): sled 뒤 12B(CarGroup 등) -> dash 구간 +12
        "pos_x": (244, "<f"), "pos_y": (248, "<f"), "pos_z": (252, "<f"),
        "speed": (256, "<f"), "power": (260, "<f"), "torque": (264, "<f"),
        "temp_fl": (268, "<f"), "temp_fr": (272, "<f"),  # 타이어 온도 (F)
        "temp_rl": (276, "<f"), "temp_rr": (280, "<f"),
        "accel": (315, "<B"), "brake": (316, "<B"), "clutch": (317, "<B"),
        "handbrake": (318, "<B"), "gear": (319, "<B"), "steer": (320, "<b"),
    },
}
_KNOWN_SIZES = {232} | set(_DASH_TABLES)


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
        self.accel_x = 0.0
        self.accel_z = 0.0
        self.vel_x = 0.0
        self.vel_z = 0.0
        self.ang_vel_y = 0.0
        self.car_ordinal = 0
        self.car_class = 0
        self.car_pi = 0
        self.handbrake = 0
        self.pos_x = 0.0
        self.pos_y = 0.0
        self.pos_z = 0.0
        for w in ("fl", "fr", "rl", "rr"):
            setattr(self, f"sr_{w}", 0.0)
            setattr(self, f"sa_{w}", 0.0)
            setattr(self, f"cs_{w}", 0.0)
            setattr(self, f"sus_{w}", 0.0)
            setattr(self, f"temp_{w}", 0.0)

    def wheels(self):
        """4륜 데이터 스냅샷: {fl:{slip,angle,combined,sus,temp_c},...}"""
        out = {}
        for w in ("fl", "fr", "rl", "rr"):
            out[w] = {
                "slip": getattr(self, f"sr_{w}"),
                "angle": getattr(self, f"sa_{w}"),
                "combined": getattr(self, f"cs_{w}"),
                "sus": getattr(self, f"sus_{w}"),
                "temp_c": (getattr(self, f"temp_{w}") - 32) * 5 / 9,  # F->C
            }
        return out

    @property
    def alive(self):
        """차량 탑승 중 판정: is_race_on 대신 max_rpm>0 && 최근 수신."""
        return self.max_rpm > 0 and (time.time() - self.last_rx) < 0.5

    @property
    def rpm_ratio(self):
        if self.max_rpm <= self.idle_rpm:
            return 0.0
        return max(0.0, (self.rpm - self.idle_rpm) / (self.max_rpm - self.idle_rpm))

    @property
    def lat_g(self):
        """횡가속도 (G 단위, 우측 +)."""
        return self.accel_x / 9.81

    @property
    def drift_deg(self):
        """드리프트 각(슬립 앵글, 도 단위) — 로컬 속도벡터와 차체 전방의 각.

        저속(5m/s 미만)에선 노이즈라 0 처리. 우측 슬라이드 +.
        """
        import math
        if self.speed < 5.0:
            return 0.0
        return math.degrees(math.atan2(self.vel_x, max(0.1, abs(self.vel_z))))


class TelemetryListener(threading.Thread):
    def __init__(self, port, state: TelemetryState, log=print):
        super().__init__(daemon=True, name="telemetry")
        self.state = state
        self.log = log
        self._stop = threading.Event()
        self._warned_sizes = set()
        # 바인드는 스레드 시작 전에 — 포트 점유 시 조용히 죽지 않고 즉시 실패
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.bind(("127.0.0.1", port))
        except OSError as e:
            self.sock.close()
            raise RuntimeError(
                f"UDP {port} 바인드 실패 ({e}) — 다른 인스턴스/SimHub가 점유 중이거나 "
                f"config.toml [telemetry].port 변경 필요") from e
        self.sock.settimeout(0.5)

    def stop(self):
        self._stop.set()

    def run(self):
        s = self.state
        while not self._stop.is_set():
            try:
                data, _ = self.sock.recvfrom(1024)
            except socket.timeout:
                continue
            except OSError:
                break  # 소켓이 닫힘 (종료 경로)
            n = len(data)
            if n not in _KNOWN_SIZES:
                if n not in self._warned_sizes:
                    self._warned_sizes.add(n)
                    self.log(f"[telemetry] 알 수 없는 패킷 크기 {n}B — 무시 "
                             f"(포맷 테이블 추가 필요)")
                continue
            fields = dict(_SLED)
            fields.update(_DASH_TABLES.get(n, {}))
            for name, (off, fmt) in fields.items():
                if off + struct.calcsize(fmt) <= n:
                    setattr(s, name, struct.unpack_from(fmt, data, off)[0])
            s.packet_size = n
            s.last_rx = time.time()
        self.sock.close()
