"""기능 B: RS50 rev-light (10x RGB) 직접 제어.

프로토콜 (refs/trueforce-linux-driver 문서 §9 + 드라이버 hidpp_dd_lightsync_apply_slot):
  0x807A (LIGHTSYNC effect) + 0x807B (RGB zone config), 슬롯 0-4.

  초기화(1회): 807A fn0/1/2, 807B fn0 조회 -> 807A fn4 `00 0A 00` -> 807A fn7
  프레임 쓰기(펌웨어가 SW 제어권을 회수하므로 매번 전체 재전송):
    1. 807A fn3 SET_EFFECT(5=static)   [short]
    2. 807A fn6 PRE_CONFIG             [long,  00 01 00 0A 00 00]
    3. 807B fn2 SET_SLOT_CONFIG        [vlong, slot byte5 RGB(LED10->LED1 역순)]
    4. 807B fn3 ACTIVATE(slot)         [short] <- commit보다 먼저
    5. 807A fn6 COMMIT                 [long,  00 01 00 0A 00 0A]
    6. 807A fn7 REFRESH                [short]

  byte5 = 슬롯 애니메이션 방향(1-4만 유효, 0/5는 err 2) — main.py가 시작 시
  슬롯 0을 읽어 그 값을 승계함 (수동 지정은 Rs50Led(direction=) 인자).

[주의] LED 트래픽은 FFB 설정과 HID++ 인터페이스를 공유 — 폭주 시 FFB 기아.
  -> LED 상태(점등 개수/블링크 위상)가 바뀔 때만 전송 + 최소 간격 제한.
[주의] 지정 슬롯의 G HUB 커스텀 패턴(CUSTOM n)을 덮어쓴다. 기본 슬롯 4(CUSTOM 5).
"""
import math
import time

from src.hidpp import Rs50Hidpp

NUM_LEDS = 10
FEAT_EFFECT = 0x807A
FEAT_RGB = 0x807B

GREEN = (0, 255, 0)
YELLOW = (255, 160, 0)
RED = (255, 0, 0)
BLUE = (0, 60, 255)
ORANGE = (255, 80, 0)
OFF = (0, 0, 0)

# 색상 프리셋: ltr = 좌->우 채움용 LED별 색(10), center = 양끝->중앙 쌍별 색(5),
# blink = 오버레브 점멸색
PRESETS = {
    "classic": {"ltr": [GREEN] * 4 + [YELLOW] * 4 + [RED] * 2,
                "center": [GREEN, GREEN, YELLOW, YELLOW, RED],
                "blink": RED, "wave": (0, 150, 255)},
    "f1":      {"ltr": [GREEN] * 3 + [RED] * 4 + [BLUE] * 3,
                "center": [GREEN, GREEN, RED, RED, BLUE],
                "blink": (185, 0, 255),  # 풀 충전 시 전체 보라 점멸 (실차 F1식)
                "wave": (0, 60, 255)},
    "porsche": {"ltr": [ORANGE] * 10,
                "center": [ORANGE] * 5,
                "blink": RED, "wave": (255, 60, 0)},
}


class Rs50Led:
    def __init__(self, dev: Rs50Hidpp = None, slot=0, min_interval=0.1,
                 preset="f1", direction=4, keepalive=None, fast=True):
        # keepalive=None이 기본: 슬롯 0 "내용" 갱신 방식은 재전송이 불필요하고
        # 상시 전송은 FFB를 굶김. (킵얼라이브는 구 슬롯4/activate 방식의 유물)
        self.fast = fast
        self.dev = dev or Rs50Hidpp()
        self.idx_a = self.dev.feature_index(FEAT_EFFECT)
        self.idx_b = self.dev.feature_index(FEAT_RGB)
        self.slot = slot
        self.min_interval = min_interval
        self.preset = PRESETS.get(preset, PRESETS["classic"])
        self.direction = direction
        # G HUB/펌웨어가 ~1초 내에 표시 소유권을 회수함 (실기 관찰) ->
        # 상태 불변이어도 이 주기로 마지막 프레임 재전송해 소유권 유지
        self.keepalive = keepalive
        self._last_colors = None
        self._last_frame = None
        self._last_send = 0.0
        self._saved = None
        self._init_subsystem()

    def _init_subsystem(self):
        """G HUB 시작 시퀀스 재현 (fn4가 핵심 arm 스텝으로 추정)."""
        d, a, b = self.dev, self.idx_a, self.idx_b
        for feat, fn in ((a, 0), (a, 1), (a, 2), (b, 0)):
            try:
                d.call(feat, fn)
            except Exception:
                pass
        try:
            d.call(a, 4, bytes([0x00, NUM_LEDS, 0x00]))  # SET_LEDS (err 5 무시)
        except Exception:
            pass
        try:
            d.call(a, 7, bytes([0, 0, 0]))               # ENABLE
        except Exception:
            pass

    # ---- 저수준 ----

    def read_slot(self, slot):
        """슬롯 설정 백업용 읽기: (slot, byte5, [(r,g,b) x10 LED1..10])."""
        p = self.dev.call(self.idx_b, 1, bytes([slot]))
        b5 = p[1]
        rev = [tuple(p[2 + i * 3: 5 + i * 3]) for i in range(NUM_LEDS)]
        return slot, b5, list(reversed(rev))  # 프로토콜 역순 -> LED1..10

    def write_frame(self, colors, direction=None):
        """colors: [(r,g,b) x10] LED1..10 순서. 전체 재중재 시퀀스로 전송."""
        d, a, b = self.dev, self.idx_a, self.idx_b
        t, r = 0.3, 1  # LED 경로는 짧은 타임아웃 — 블로킹으로 호출측을 굳히지 않기
        b5 = self.direction if direction is None else direction
        rgb = b"".join(bytes(c) for c in reversed(colors))  # LED10 -> LED1
        pre = bytes([0x00, 0x01, 0x00, NUM_LEDS, 0x00, 0x00])
        commit = bytes([0x00, 0x01, 0x00, NUM_LEDS, 0x00, NUM_LEDS])
        d.call(a, 3, bytes([0x05, 0, 0]), t, r)                   # SET_EFFECT static
        d.call(a, 6, pre, t, r)                                   # PRE_CONFIG
        d.call(b, 2, bytes([self.slot, b5]) + rgb + b"\x00" * 26, t, r)
        d.call(b, 3, bytes([self.slot, 0, 0]), t, r)              # ACTIVATE slot
        d.call(a, 6, commit, t, r)                                # COMMIT (byte5=0x0A)
        d.call(a, 7, bytes([0, 0, 0]), t, r)                      # REFRESH

    # ---- 경량 레벨 경로 (주행 중 전용 — FFB 안전) ----
    # G PRO식 프로토콜을 RS50이 수용함을 실기 확인 (2026-07-20).
    # 색/채움방향은 슬롯0+이펙트에서 오고, "몇 칸(0-10)"만 fire-and-forget 전송.
    # NVM 미접촉이라 G HUB 실측 127Hz까지도 FFB 무사.

    def _short_ff(self, fn, params=b"\x00\x00\x00"):
        from src.hidpp import DEV_IDX, SW_ID
        req = bytes([0x10, DEV_IDX, self.idx_a, ((fn & 0xF) << 4) | SW_ID]) + params
        self.dev.h_short.write(req + b"\x00" * (7 - len(req)))

    def arm_level(self, effect=2):
        """레벨 모드 진입 (1회 암 버스트). effect: 1=중앙발산 2=중앙수렴 3=RL 4=LR."""
        with self.dev._lock:
            for fn, pr in ((0, b"\x00\x00\x00"), (1, b"\x00\x00\x00"),
                           (2, b"\x00\x00\x00"), (3, bytes([effect, 0, 0])),
                           (0, b"\x00\x00\x00")):
                self._short_ff(fn, pr)
                time.sleep(0.005)

    def set_level(self, v):
        """점등 칸수 0-10 전송 (fire-and-forget 페어, 응답 대기 없음)."""
        from src.hidpp import DEV_IDX, SW_ID
        with self.dev._lock:
            self._short_ff(2)
            p = bytes([0x00, 0x01, 0x00, NUM_LEDS, 0x00, v & 0xFF])
            req = bytes([0x11, DEV_IDX, self.idx_a, (6 << 4) | SW_ID]) + p
            self.dev.h_long.write(req + b"\x00" * (20 - len(req)))

    def write_fast(self, colors):
        """중간 갱신: fn2 쓰기 + fn6 commit + fn7 refresh (3콜).

        fn2+fn7만으로는 표시 반영 안 됨(실측) — commit이 표시 적용 단계로 추정.
        풀 시퀀스 대비 깜빡임/FFB 부하 절반. 실패 시 config로 full 전환 가능.
        """
        d, a, b = self.dev, self.idx_a, self.idx_b
        t, r = 0.3, 1
        rgb = b"".join(bytes(c) for c in reversed(colors))
        commit = bytes([0x00, 0x01, 0x00, NUM_LEDS, 0x00, NUM_LEDS])
        d.call(b, 2, bytes([self.slot, self.direction]) + rgb + b"\x00" * 26, t, r)
        d.call(a, 6, commit, t, r)
        d.call(a, 7, bytes([0, 0, 0]), t, r)

    # ---- 백업/복원 ----

    def backup(self):
        self._saved = self.read_slot(self.slot)

    def restore(self):
        if self._saved:
            _, b5, colors = self._saved
            self.write_frame(colors, b5)

    # ---- rev-light 렌더링 ----

    def frame_for_ratio(self, lit_ratio, mode="center", blink_off=False):
        """lit_ratio 0..1 -> LED1..10 색 배열 (프리셋 색상 사용)."""
        if blink_off:
            return [OFF] * NUM_LEDS
        colors = [OFF] * NUM_LEDS
        if mode == "ltr":
            n = round(lit_ratio * NUM_LEDS)
            for i in range(n):
                colors[i] = self.preset["ltr"][i]
        else:  # center: 양끝에서 중앙으로 쌍 단위 채움
            pairs = round(lit_ratio * 5)
            for p in range(pairs):
                colors[p] = self.preset["center"][p]
                colors[NUM_LEDS - 1 - p] = self.preset["center"][p]
        return colors

    def _wave_frame(self, now, speed=0.8):
        """아이들 물결: 은은한 밝기 파동이 좌->우로 흐름."""
        base = self.preset.get("wave", (0, 60, 255))
        colors = []
        for i in range(NUM_LEDS):
            ph = math.sin(2 * math.pi * (now * speed - i / NUM_LEDS * 1.4))
            b = 0.06 + 0.55 * max(0.0, ph) ** 2  # 골짜기 은은, 마루 선명
            colors.append(tuple(int(c * b) for c in base))
        return colors

    def set_rpm(self, rpm_ratio, start_ratio=0.5, blink_ratio=0.95,
                mode="center", blink_hz=10.0, idle=False):
        """텔레메트리 루프에서 주기 호출. 상태 변화 시에만 실제 전송.

        idle=True(메뉴) = RGB 물결. 주행 중 = 경량 레벨 경로 (FFB 안전).
        """
        now = time.time()
        if not idle:
            # ---- 주행: 레벨 경로 ----
            if getattr(self, "_path", None) != "level":
                self.arm_level()
                self._path = "level"
                self._last_frame = None
            if rpm_ratio >= blink_ratio:
                if blink_hz > 0:
                    lv = 10 if (int(now * blink_hz * 2) % 2) == 0 else 0
                else:
                    lv = 10
            elif rpm_ratio < start_ratio:
                lv = 0
            else:
                lv = min(10, max(1, round(
                    (rpm_ratio - start_ratio) / (blink_ratio - start_ratio) * 10)))
            key = ("lv", lv)
            if key == self._last_frame or now - self._last_send < 0.03:
                return
            self.set_level(lv)
            self._last_frame = key
            self._last_send = now
            return
        # ---- 메뉴: RGB 물결 경로 ----
        if getattr(self, "_path", None) != "rgb":
            # 레벨 모드에서 복귀: effect 5(static) 포함 풀 시퀀스로 표시 기준 재설정
            try:
                self.set_level(0)
                self.write_frame([OFF] * NUM_LEDS)
            except Exception:
                pass
            self._path = "rgb"
            self._last_frame = None
        if idle:
            # 메뉴 전용(FFB 비활성) -> 10fps로 부드럽게
            key = ("wave", int(now * 10))
            colors = self._wave_frame(now)
        elif rpm_ratio >= blink_ratio:
            # 오버레브: 점멸색 전체 <-> 소등 (F1식 '지금 변속' 신호)
            blink_off = (int(now * blink_hz * 2) % 2) == 1
            key = ("blink", blink_off)
            colors = [OFF] * NUM_LEDS if blink_off else [self.preset["blink"]] * NUM_LEDS
        elif rpm_ratio < start_ratio:
            key = ("off",)
            colors = [OFF] * NUM_LEDS
        else:
            lit = (rpm_ratio - start_ratio) / (blink_ratio - start_ratio)
            steps = 5 if mode == "center" else NUM_LEDS
            q = min(steps, max(1, round(lit * steps)))  # 시작 즉시 1단계 점등
            key = ("lit", q)
            colors = self.frame_for_ratio(q / steps, mode)

        if self.keepalive:
            stale = now - self._last_send >= self.keepalive
        else:
            stale = False  # keepalive 비활성 (표시 소유 경쟁자 없음 전제)
        if (key == self._last_frame and not stale) \
                or now - self._last_send < self.min_interval:
            return
        if self.fast:
            self.write_fast(colors)
        else:
            self.write_frame(colors)
        self._last_frame = key
        self._last_send = now
