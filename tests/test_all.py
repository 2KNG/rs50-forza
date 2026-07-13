"""게임/휠 없이 도는 단위 테스트 스위트.

usage: python -m unittest tests.test_all -v
"""
import json
import math
import socket
import struct
import time
import unittest
import urllib.request
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.autoshift import AutoShiftFSM, AUTO, MANUAL
from src.telemetry import TelemetryListener, TelemetryState
from src.ledctl import Rs50Led, PRESETS, OFF
from src.webui import WebUI, _sanitize


class FakeState:
    def __init__(self):
        self.gear = 3
        self.speed = 30.0
        self.max_rpm = 8000.0
        self.idle_rpm = 800.0
        self.rpm = 4000.0
        self.accel = 0
        self.brake = 0
        self.last_rx = time.time()
        self._alive = True

    @property
    def alive(self):
        return self._alive

    @property
    def rpm_ratio(self):
        return (self.rpm - self.idle_rpm) / (self.max_rpm - self.idle_rpm)

    def set_ratio(self, r):
        self.rpm = self.idle_rpm + r * (self.max_rpm - self.idle_rpm)


class FakeShifter:
    def __init__(self, state, apply=True):
        self.state = state
        self.apply = apply
        self.ups = 0
        self.downs = 0

    def up(self):
        self.ups += 1
        if self.apply:
            self.state.gear += 1
        return True

    def down(self):
        self.downs += 1
        if self.apply:
            self.state.gear = max(0, self.state.gear - 1)
        return True


def make_fsm(state, shifter, **over):
    cfg = {"upshift_ratio": 0.88, "downshift_ratio": 0.35,
           "min_shift_interval_s": 0.0, "max_gear": 8,
           "timeout_s": 0.3, "reverse_max_kmh": 15}
    cfg.update(over)
    return AutoShiftFSM(state, shifter, cfg, log=lambda m: None)


class TestFSM(unittest.TestCase):
    def test_upshift_needs_accel(self):
        st, sh = FakeState(), None
        sh = FakeShifter(st)
        fsm = make_fsm(st, sh)
        st.set_ratio(0.90)
        st.accel = 0
        fsm.tick()
        self.assertEqual(sh.ups, 0, "스로틀 없이 업시프트 금지")
        st.accel = 200
        fsm.tick()
        self.assertEqual(sh.ups, 1)

    def test_coast_downshift_and_speed_guard(self):
        st = FakeState()
        sh = FakeShifter(st)
        fsm = make_fsm(st, sh)
        st.set_ratio(0.2)
        st.speed = 20.0  # 코스팅
        fsm.tick()
        self.assertEqual(sh.downs, 1, "코스트 다운시프트")
        st2 = FakeState()
        sh2 = FakeShifter(st2)
        fsm2 = make_fsm(st2, sh2)
        st2.set_ratio(0.2)
        st2.speed = 1.0  # 서행 -> 금지
        fsm2.tick()
        self.assertEqual(sh2.downs, 0, "정차 중 다운시프트 금지")

    def test_neutral_and_reverse_ignored(self):
        for g in (0, 11):
            st = FakeState()
            st.gear = g
            sh = FakeShifter(st, apply=False)
            fsm = make_fsm(st, sh)
            st.set_ratio(0.95)
            st.accel = 255
            fsm.tick()
            self.assertEqual(sh.ups + sh.downs, 0, f"기어 {g}에서 관여 금지")

    def test_manual_override_and_timeout(self):
        st = FakeState()
        sh = FakeShifter(st, apply=False)
        fsm = make_fsm(st, sh, timeout_s=0.15)
        fsm.on_paddle("down")
        self.assertEqual(fsm.mode, MANUAL)
        st.set_ratio(0.95)
        st.accel = 255
        fsm.tick()
        self.assertEqual(sh.ups, 0, "수동 중 자동변속 금지")
        time.sleep(0.2)
        fsm.tick()
        self.assertEqual(fsm.mode, AUTO, "타임아웃 복귀")

    def test_up_hold_returns_auto(self):
        st = FakeState()
        fsm = make_fsm(st, FakeShifter(st))
        fsm.on_paddle("up")
        self.assertEqual(fsm.mode, MANUAL)
        self.assertTrue(fsm.on_hold("up"))
        self.assertEqual(fsm.mode, AUTO)

    def test_paddle_veto_window(self):
        st = FakeState()
        sh = FakeShifter(st, apply=False)
        fsm = make_fsm(st, sh, timeout_s=0.01)
        fsm.on_paddle("up")
        time.sleep(0.05)
        fsm.tick()  # AUTO 복귀됨
        st.set_ratio(0.95)
        st.accel = 255
        fsm.tick()  # 패들 에지 0.3s 이내 -> 베토
        self.assertEqual(sh.ups, 0, "패들 직후 베토 창")
        time.sleep(0.3)
        fsm.tick()
        self.assertEqual(sh.ups, 1)

    def test_reverse_engage_and_cancel(self):
        st = FakeState()
        st.gear = 3
        st.speed = 1.0
        st.last_rx = time.time()
        sh = FakeShifter(st)
        fsm = make_fsm(st, sh)
        self.assertTrue(fsm.on_hold("down"))
        fsm.tick()
        self.assertGreater(sh.downs, 0)
        fsm.on_paddle("up")  # 취소
        self.assertEqual(fsm._reverse_until, 0.0)

    def test_reverse_refusals_return_false(self):
        st = FakeState()
        st.gear = 3
        st.speed = 10.0  # 36km/h
        st.last_rx = time.time()
        fsm = make_fsm(st, FakeShifter(st))
        self.assertFalse(fsm.on_hold("down"), "속도 초과 -> False(재시도용)")
        st.speed = 1.0
        st.last_rx = time.time() - 0.5  # 잔상
        self.assertFalse(fsm.on_hold("down"), "잔상 텔레메트리 -> False")
        st.last_rx = time.time()
        self.assertTrue(fsm.on_hold("down"))

    def test_reverse_deadline_scales(self):
        st = FakeState()
        st.gear = 8
        st.speed = 1.0
        st.last_rx = time.time()
        fsm = make_fsm(st, FakeShifter(st))
        t0 = time.time()
        fsm.on_hold("down")
        self.assertGreater(fsm._reverse_until - t0, 4.5)

    def test_top_gear_learning_and_reset(self):
        st = FakeState()
        st.gear = 6
        sh = FakeShifter(st, apply=False)  # 게임이 반영 안 함 = 톱기어
        fsm = make_fsm(st, sh, min_shift_interval_s=0.0)
        st.set_ratio(0.95)
        st.accel = 255
        for _ in range(2):  # 2회 실패 유도
            fsm.tick()               # 명령
            fsm._last_shift -= 2.0   # 반영 대기(1.5s) 건너뛰기
            fsm.tick()               # 실패 판정
        self.assertEqual(fsm._top_gear, 6, "톱기어 학습")
        fsm.tick()
        self.assertEqual(sh.ups, 2, "학습 후 재발사 금지")
        st.max_rpm = 7000.0  # 차량 교체
        fsm.tick()
        self.assertIsNone(fsm._top_gear, "차량 교체 시 학습 리셋")


class TestTelemetry(unittest.TestCase):
    PORT = 15607

    def _packet(self, rpm=5000.0, gear=3, size=324):
        pkt = bytearray(size)
        struct.pack_into("<i", pkt, 0, 1)
        struct.pack_into("<f", pkt, 8, 8000.0)
        struct.pack_into("<f", pkt, 12, 800.0)
        struct.pack_into("<f", pkt, 16, rpm)
        if size == 324:
            struct.pack_into("<f", pkt, 256, 30.0)
            pkt[315] = 100
            pkt[319] = gear
        return bytes(pkt)

    def test_parse_and_unknown_size(self):
        state = TelemetryState()
        warns = []
        lis = TelemetryListener(self.PORT, state, log=warns.append)
        lis.start()
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.sendto(self._packet(rpm=6000.0, gear=4), ("127.0.0.1", self.PORT))
        time.sleep(0.15)
        self.assertAlmostEqual(state.rpm, 6000.0, delta=1)
        self.assertEqual(state.gear, 4)
        self.assertTrue(state.alive)
        # 알 수 없는 크기 -> 상태 불변 + 1회 경고
        s.sendto(b"\x00" * 100, ("127.0.0.1", self.PORT))
        s.sendto(b"\x00" * 100, ("127.0.0.1", self.PORT))
        time.sleep(0.15)
        self.assertEqual(state.gear, 4, "미지 패킷이 상태를 오염시키면 안 됨")
        self.assertEqual(len([w for w in warns if "알 수 없는" in w]), 1, "경고 1회만")
        lis.stop()
        s.close()

    def test_port_conflict_raises(self):
        state = TelemetryState()
        lis = TelemetryListener(self.PORT + 1, state)
        with self.assertRaises(RuntimeError):
            TelemetryListener(self.PORT + 1, TelemetryState())
        lis.sock.close()


class TestLedRender(unittest.TestCase):
    def _led(self, preset="f1"):
        led = Rs50Led.__new__(Rs50Led)  # 하드웨어 없이 렌더 로직만
        led.preset = PRESETS[preset]
        led.min_interval = 0.0
        led.keepalive = None
        led.fast = True
        led._last_frame = None
        led._last_send = 0.0
        led.sent = []
        led.write_fast = lambda c: led.sent.append(("fast", list(c)))
        led.write_frame = lambda c, direction=None: led.sent.append(("full", list(c)))
        return led

    def test_ltr_fill_counts(self):
        led = self._led()
        for lit, expect in ((0.0, 0), (0.5, 5), (1.0, 10)):
            frame = led.frame_for_ratio(lit, mode="ltr")
            self.assertEqual(sum(1 for c in frame if c != OFF), expect)

    def test_f1_colors(self):
        led = self._led()
        frame = led.frame_for_ratio(1.0, mode="ltr")
        self.assertEqual(frame[0], (0, 255, 0))
        self.assertEqual(frame[4], (255, 0, 0))
        self.assertEqual(frame[9], PRESETS["f1"]["ltr"][9])

    def test_set_rpm_dedup(self):
        led = self._led()
        led.set_rpm(0.6)
        led.set_rpm(0.6)  # 같은 단계 -> 전송 1회만
        self.assertEqual(len(led.sent), 1)
        led.set_rpm(0.7)  # 단계 변화 -> 추가 전송
        self.assertEqual(len(led.sent), 2)

    def test_idle_wave_animates(self):
        led = self._led()
        led.set_rpm(0.0, idle=True)
        time.sleep(0.12)
        led.set_rpm(0.0, idle=True)
        self.assertGreaterEqual(len(led.sent), 2, "물결은 시간에 따라 재전송")


class TestWebUI(unittest.TestCase):
    def test_sanitize(self):
        out = _sanitize({"a": float("nan"), "b": float("inf"), "c": 1.5,
                         "d": {"e": float("-inf")}, "s": "x", "l": [1, 2]})
        self.assertEqual(out["a"], 0.0)
        self.assertEqual(out["b"], 0.0)
        self.assertEqual(out["c"], 1.5)
        self.assertEqual(out["d"]["e"], 0.0)
        json.dumps(out, allow_nan=False)  # 표준 JSON 보장

    def test_server_endpoints(self):
        provider = lambda: {"rpm": float("nan"), "alive": True, "events": []}
        ui = WebUI(provider, port=18777)
        ui.start()
        time.sleep(0.4)
        page = urllib.request.urlopen("http://127.0.0.1:18777/", timeout=3).read()
        self.assertIn(b"RS50", page)
        state = json.loads(urllib.request.urlopen(
            "http://127.0.0.1:18777/state", timeout=3).read())
        self.assertEqual(state["rpm"], 0.0, "NaN 무해화")
        with self.assertRaises(Exception):
            urllib.request.urlopen("http://127.0.0.1:18777/nope", timeout=3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
