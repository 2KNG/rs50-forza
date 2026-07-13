"""키보드 인젝션으로 시프트 업/다운 수행 (pydirectinput).

포커스 가드: 전면 창 제목에 지정 문자열(기본 "forza")이 없으면 인젝션을
건너뛴다 — 알트탭 중 다른 앱에 e/q가 입력되는 사고 방지.
"""
import ctypes
import threading
import time

import pydirectinput

pydirectinput.PAUSE = 0        # 내부 기본 딜레이 제거
pydirectinput.FAILSAFE = False  # 마우스가 화면 모서리에 있어도 예외 금지


def _foreground_title():
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(256)
    ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
    return buf.value


class Shifter:
    def __init__(self, key_up="e", key_down="q", press_ms=30, focus_guard="forza",
                 log=print):
        self.key_up = key_up
        self.key_down = key_down
        self.press_s = press_ms / 1000.0
        self.focus_guard = (focus_guard or "").lower()
        self.log = log
        self._lock = threading.Lock()
        self._last_skip_log = 0.0

    def _focused(self):
        if not self.focus_guard:
            return True
        try:
            return self.focus_guard in _foreground_title().lower()
        except Exception:
            return True  # 판정 불가 시 인젝션 허용 (기능 우선)

    def _press(self, key):
        if not self._focused():
            now = time.time()
            if now - self._last_skip_log > 10:
                self._last_skip_log = now
                self.log(f"[shifter] 게임 창 비활성 — '{key}' 인젝션 보류 "
                         f"(가드: '{self.focus_guard}')")
            return False
        with self._lock:
            pydirectinput.keyDown(key)
            try:
                time.sleep(self.press_s)
            finally:
                pydirectinput.keyUp(key)  # 예외가 나도 키가 눌린 채 남지 않게
        return True

    def up(self):
        return self._press(self.key_up)

    def down(self):
        return self._press(self.key_down)
