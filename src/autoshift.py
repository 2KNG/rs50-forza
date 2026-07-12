"""기능 A: 오토<->매뉴얼 패들 핸드오버 상태머신.

  AUTO            : 텔레메트리 기반 자동 변속 (키 인젝션)
  MANUAL_OVERRIDE : 패들 입력 감지 시 진입, timeout_s 동안 추가 입력 없으면 AUTO 복귀
                    (입력마다 타이머 리셋), 업패들 hold_s 홀드 시 즉시 AUTO 복귀

게임은 Manual 변속 설정 고정. 물리 패들 입력은 그대로 게임에 들어가며
이 프로세스는 관찰만 한다.
"""
import time

AUTO = "AUTO"
MANUAL = "MANUAL_OVERRIDE"


class AutoShiftFSM:
    def __init__(self, state, shifter, cfg, log=print):
        """state: TelemetryState, shifter: Shifter, cfg: dict(config[auto]/[override])"""
        self.t = state
        self.shifter = shifter
        self.log = log
        self.mode = AUTO
        self.last_paddle = 0.0
        self.timeout_s = cfg.get("timeout_s", 7.0)
        self.up_ratio = cfg.get("upshift_ratio", 0.88)
        self.down_ratio = cfg.get("downshift_ratio", 0.35)
        self.min_interval = cfg.get("min_shift_interval_s", 0.6)
        self.max_gear = cfg.get("max_gear", 8)
        self._last_shift = 0.0
        self._pending_gear = None   # 직전 명령의 기대 기어 (반영 확인 전 재발사 방지)
        self._pending_from = None
        self._up_fails = {}         # gear -> 연속 미반영 횟수 (실질 톱기어 학습)
        self._top_gear = None
        self._last_max_rpm = 0.0

    def on_paddle(self, direction):
        """PaddleWatcher 콜백 (패들 눌림 에지)."""
        self.last_paddle = time.time()
        if self.mode != MANUAL:
            self.mode = MANUAL
            self.log(f"[FSM] -> MANUAL_OVERRIDE (패들 {direction})")

    def on_hold(self, direction):
        """시프트업 패들 장시간 홀드 -> 즉시 AUTO 복귀 (실차 +패들 홀드 방식)."""
        if direction == "up" and self.mode == MANUAL:
            self.mode = AUTO
            self._last_shift = time.time()  # 복귀 직후 즉발 변속 방지
            self.log("[FSM] -> AUTO (시프트업 패들 홀드)")

    def _resolve_pending(self, now, gear):
        """직전 변속 명령의 반영 여부 확인. 반환: True=변속 판단 진행 가능."""
        if self._pending_gear is None:
            return True
        if gear == self._pending_gear:
            if self._pending_from is not None:
                self._up_fails.pop(self._pending_from, None)
            self._pending_gear = self._pending_from = None
            return True
        if now - self._last_shift < 1.5:
            return False  # 반영 대기
        # 미반영 -> 업시프트였다면 실질 톱기어 학습 (없는 기어로 계속 E 누르는 것 방지)
        if (self._pending_from is not None
                and self._pending_gear == self._pending_from + 1):
            n = self._up_fails.get(self._pending_from, 0) + 1
            self._up_fails[self._pending_from] = n
            if n >= 2 and self._top_gear != self._pending_from:
                self._top_gear = self._pending_from
                self.log(f"[AUTO] {self._top_gear}단 = 이 차의 실질 최고 기어로 학습")
        self._pending_gear = self._pending_from = None
        return True

    def tick(self):
        """메인 루프에서 주기 호출 (~60Hz)."""
        now = time.time()

        if self.mode == MANUAL:
            if now - self.last_paddle >= self.timeout_s:
                self.mode = AUTO
                self.log("[FSM] -> AUTO (패들 입력 타임아웃)")
            return

        # ---- AUTO 모드 ----
        t = self.t
        # 관여 제외: 메뉴, 후진(0), 중립/비정상 기어(11+ — FH는 11=N)
        if not t.alive or t.gear == 0 or t.gear > self.max_gear:
            return
        # 차량 교체 감지 -> 학습된 톱기어 리셋
        if abs(t.max_rpm - self._last_max_rpm) > 1.0:
            self._last_max_rpm = t.max_rpm
            self._top_gear = None
            self._up_fails.clear()
        # 방금 패들 에지가 있었으면 이번 틱 인젝션 금지 (모드 전환 경합 가드)
        if now - self.last_paddle < 0.3:
            return
        if now - self._last_shift < self.min_interval:
            return
        if not self._resolve_pending(now, t.gear):
            return

        ratio = t.rpm_ratio
        accel = t.accel / 255.0
        brake = t.brake / 255.0
        gear = t.gear  # 인젝션 도중 텔레메트리 갱신에 흔들리지 않게 스냅샷

        if self._top_gear is not None and gear > self._top_gear:
            self._top_gear = None  # 수동으로 그 위 기어에 도달했다면 학습 무효
        top = self._top_gear if self._top_gear is not None else self.max_gear

        if ratio >= self.up_ratio and accel > 0.2 and gear < top:
            if self.shifter.up():
                self._last_shift = now
                self._pending_gear, self._pending_from = gear + 1, gear
                self.log(f"[AUTO] upshift {gear}->{gear+1} (ratio {ratio:.2f})")
        elif ratio <= self.down_ratio and gear > 1 and t.speed > 3.0:
            # rpm이 처지면 페달과 무관하게 다운시프트 (코스팅/제동/킥다운 공통).
            # speed 가드: 정차/서행 중 Q 스팸으로 중립/후진 진입 방지.
            if self.shifter.down():
                self._last_shift = now
                self._pending_gear, self._pending_from = gear - 1, gear
                why = "kickdown" if accel > 0.5 else ("brake" if brake > 0.3 else "coast")
                self.log(f"[AUTO] downshift {gear}->{gear-1} (ratio {ratio:.2f}, {why})")
