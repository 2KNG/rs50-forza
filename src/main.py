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

    monitor_only = "--monitor" in sys.argv
    if monitor_only:
        log("[모드] 모니터링 전용 — 패들 관찰/키 인젝션/LED 전부 비활성 (휠 접촉 0)")

    watcher = None
    pcfg = cfg.get("paddles", {})
    pkeys = ("byte_up", "bit_up", "byte_down", "bit_down")
    missing = [k for k in pkeys if pcfg.get(k) is None]
    if monitor_only:
        pass
    elif not missing:
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

    lcfg = cfg.get("led", {})
    if "--led" in sys.argv and not monitor_only:
        # 주행 중 LED 렌더링은 최종 폐기 (RS50: FFB와 LED가 USB 컨트롤 파이프
        # 공유 — 어떤 전송이든 FFB 붕괴, 실주행 확정. rev 게이지 = 웹 담당).
        # --led는 시작 시 1회만: 데스크톱 프로필 보장 + 정적 F1 그라데이션 표시.
        # 설정 불간섭 원칙: 프로필/강도 등 FFB 설정은 일절 건드리지 않는다
        # (설정의 단일 주인 = G HUB UI. HID++로 써봤자 G HUB DB가 재적용하며
        #  되돌림 — 밀당의 원인이었음). --led는 슬롯0 색 1회 재도색만.
        try:
            from src.ledctl import Rs50Led
            led = Rs50Led(slot=0, preset=lcfg.get("preset", "f1"))
            try:
                _, b5, _ = led.read_slot(0)
                led.direction = b5
            except Exception:
                pass
            led.write_frame(led.frame_for_ratio(1.0, mode="ltr"))  # 정적 그라데이션
            led.dev.close()
            log("[LED] 정적 F1 그라데이션 적용 — 이후 휠 전송 0")
        except Exception as e:
            log(f"[LED] 초기화 생략 ({e}) — 기능에 영향 없음")

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
                "lat_g": state.lat_g,
                "long_g": state.accel_z / 9.81,
                "drift_deg": state.drift_deg,
                "yaw_rate": state.ang_vel_y,
                "steer": state.steer,
                "handbrake": state.handbrake,
                "car_pi": state.car_pi,
                "car_class": state.car_class,
                "wheels": state.wheels(),
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
                if not monitor_only:
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
        listener.join(timeout=1.0)


if __name__ == "__main__":
    main()
