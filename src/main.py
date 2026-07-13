"""RS50 x Forza Horizon 6 — 메인 엔트리.

usage:
    python -m src.main            # 기능 A(오토시프트 + 패들 핸드오버)만
    python -m src.main --led      # + 기능 B(rev-light, 슬롯 0 직접 렌더링)

웹 대시보드: http://127.0.0.1:8777 (config [web])
"""
import collections
import sys
import threading
import time
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.telemetry import TelemetryListener, TelemetryState
from src.paddle_watch import PaddleWatcher
from src.shifter import Shifter
from src.autoshift import AutoShiftFSM
from src.webui import WebUI


def load_config():
    p = Path(__file__).resolve().parent.parent / "config.toml"
    with open(p, "rb") as f:
        return tomllib.load(f)


EVENTS = collections.deque(maxlen=80)


def _seg_colors(lcfg):
    """웹 스트립이 물리 휠과 같은 프리셋 색을 쓰도록 /state로 전달."""
    from src.ledctl import PRESETS
    p = PRESETS.get(lcfg.get("preset", "f1"), PRESETS["f1"])
    to_css = lambda c: f"rgb({c[0]},{c[1]},{c[2]})"
    return {"ltr": [to_css(c) for c in p["ltr"]], "blink": to_css(p["blink"])}


def log(msg):
    print(msg)
    EVENTS.append((time.strftime("%H:%M:%S"), str(msg)))


class LedThread(threading.Thread):
    """LED 갱신 전용 스레드 — HID++ 지연/오류가 변속 루프를 못 막게 격리.

    G HUB 공존 전제(TrueForce 유지). 슬롯 0(유일한 표시 슬롯)에
    LED 단계가 바뀔 때만 전송 — 순항 중 0콜/s로 FFB 간섭 최소화.
    물결은 게임 밖(텔레메트리 부재)에서만.
    """

    def __init__(self, led, state, lcfg):
        super().__init__(daemon=True, name="led")
        self.led, self.state, self.lcfg = led, state, lcfg
        self._stop = threading.Event()
        self._last_err = 0.0

    def stop(self):
        self._stop.set()

    def run(self):
        while not self._stop.is_set():
            s = self.state
            try:
                self.led.set_rpm(
                    s.rpm_ratio if s.alive else 0.0,
                    start_ratio=self.lcfg.get("start_ratio", 0.5),
                    blink_ratio=self.lcfg.get("blink_ratio", 0.95),
                    mode=self.lcfg.get("mode", "ltr"),
                    blink_hz=self.lcfg.get("blink_hz", 5.0),
                    idle=not s.alive)
            except Exception as e:
                now = time.time()
                if now - self._last_err > 5:
                    log(f"[LED] 오류(계속 진행): {e}")
                    self._last_err = now
            time.sleep(0.02)


def validate_config(cfg):
    if "telemetry" not in cfg or "port" not in cfg["telemetry"]:
        sys.exit("[config] [telemetry].port 누락 — config.toml 확인")
    sk = cfg.get("shift_keys", {})
    if "up" not in sk or "down" not in sk:
        sys.exit("[config] [shift_keys] up/down 누락 — config.toml 확인")
    lcfg = cfg.get("led", {})
    if lcfg.get("update_hz", 10) <= 0:
        sys.exit("[config] [led].update_hz 는 1 이상이어야 함")


def main():
    try:
        cfg = load_config()
    except FileNotFoundError:
        sys.exit(f"config.toml 없음 — 예상 경로: {Path(__file__).resolve().parent.parent / 'config.toml'}")
    validate_config(cfg)

    state = TelemetryState()
    try:
        listener = TelemetryListener(cfg["telemetry"]["port"], state, log=log)
    except RuntimeError as e:
        sys.exit(str(e))
    listener.start()
    log(f"텔레메트리 수신 대기: UDP {cfg['telemetry']['port']}")

    shifter = Shifter(cfg["shift_keys"]["up"], cfg["shift_keys"]["down"],
                      cfg["shift_keys"].get("press_ms", 30),
                      focus_guard=cfg["shift_keys"].get("focus_guard", "forza"),
                      log=log)
    fsm_cfg = {**cfg.get("auto", {}), **cfg.get("override", {})}
    fsm = AutoShiftFSM(state, shifter, fsm_cfg, log=log)

    watcher = None
    pcfg = cfg.get("paddles", {})
    pkeys = ("byte_up", "bit_up", "byte_down", "bit_down")
    missing = [k for k in pkeys if pcfg.get(k) is None]
    if not missing:
        try:
            watcher = PaddleWatcher(pcfg["byte_up"], pcfg["bit_up"],
                                    pcfg["byte_down"], pcfg["bit_down"],
                                    on_paddle=fsm.on_paddle, on_hold=fsm.on_hold,
                                    hold_s=cfg.get("override", {}).get("hold_to_auto_s", 2.0),
                                    log=log)
            watcher.start()
            log("패들 관찰 시작 (패들=수동 / 업패들 홀드·타임아웃=자동복귀)")
        except RuntimeError as e:
            log(f"[경고] 패들 관찰 불가 ({e}) — AUTO 전용 동작")
    elif len(missing) < len(pkeys):
        log(f"[경고] [paddles] 불완전 ({', '.join(missing)} 누락) — AUTO 전용 동작")
    else:
        log("[경고] [paddles] 미설정 — tools/paddle_map.py 로 실측 후 기입 (AUTO 전용 동작)")

    led = led_thread = None
    lcfg = cfg.get("led", {})
    if "--led" in sys.argv:
        # LED 초기화 실패(휠 절전/부재/응답 없음)해도 앱은 변속 기능으로 계속 동작
        try:
            from src.ledctl import Rs50Led
            led = Rs50Led(slot=0, min_interval=1.0 / lcfg.get("update_hz", 10),
                          preset=lcfg.get("preset", "f1"),
                          keepalive=None,
                          fast=lcfg.get("fast_updates", True))
            try:
                _, b5, _ = led.read_slot(0)
                led.direction = b5  # 슬롯 0 고유 byte5 유지
            except Exception:
                pass
            led.write_frame(led.frame_for_ratio(0))  # 풀 시퀀스 1회: 표시 상태 정렬
            led_thread = LedThread(led, state, lcfg)
            led_thread.start()
            log("LED rev-light 활성 (슬롯 0 직접, 변화시에만 전송, G HUB 공존)")
        except Exception as e:
            led = led_thread = None
            log(f"[LED] 초기화 실패 ({e}) — LED 없이 계속 진행")

    wcfg = cfg.get("web", {})
    if wcfg.get("enabled", True):
        def provider():
            return {
                "alive": state.alive, "rpm": state.rpm, "max_rpm": state.max_rpm,
                "ratio": state.rpm_ratio, "gear": state.gear,
                "speed_kmh": state.speed * 3.6, "accel": state.accel,
                "brake": state.brake, "mode": fsm.mode,
                "start_ratio": lcfg.get("start_ratio", 0.5),
                "blink_ratio": lcfg.get("blink_ratio", 0.95),
                "blink_hz": lcfg.get("blink_hz", 5),
                "seg_colors": _seg_colors(lcfg),
                "events": list(EVENTS),
            }
        port = wcfg.get("port", 8777)
        WebUI(provider, port, host=wcfg.get("host", "127.0.0.1"), log=log).start()
        log(f"웹 대시보드: http://127.0.0.1:{port}")

    print("실행 중... Ctrl+C로 종료")
    last_hb = 0.0
    last_tick_err = 0.0
    try:
        while True:
            try:
                fsm.tick()
            except Exception as e:
                now = time.time()
                if now - last_tick_err > 5:
                    log(f"[FSM] 오류(계속 진행): {e}")
                    last_tick_err = now
            now = time.time()
            if now - last_hb >= 30:
                last_hb = now
                print(f"[HB] telem={'OK' if state.alive else '-'} "
                      f"ratio={state.rpm_ratio:.2f} gear={state.gear} mode={fsm.mode}")
            time.sleep(1 / 120)
    except KeyboardInterrupt:
        pass
    finally:
        listener.stop()
        if watcher is not None:
            watcher.stop()
            watcher.join(timeout=1.0)
        if led_thread is not None:
            led_thread.stop()
            led_thread.join(timeout=2.0)
        if led is not None:
            try:
                # 종료 시 풀 F1 그라데이션을 정적으로 남김 (주차 상태 표시)
                led.write_frame(led.frame_for_ratio(1.0, mode="ltr"))
            except Exception:
                pass
            led.dev.close()
        listener.join(timeout=1.0)


if __name__ == "__main__":
    main()
