"""키보드 인젝션으로 시프트 업/다운 수행 (pydirectinput)."""
import threading
import time

import pydirectinput

pydirectinput.PAUSE = 0  # 내부 기본 딜레이 제거


class Shifter:
    def __init__(self, key_up="e", key_down="q", press_ms=30):
        self.key_up = key_up
        self.key_down = key_down
        self.press_s = press_ms / 1000.0
        self._lock = threading.Lock()

    def _press(self, key):
        with self._lock:
            pydirectinput.keyDown(key)
            time.sleep(self.press_s)
            pydirectinput.keyUp(key)

    def up(self):
        self._press(self.key_up)

    def down(self):
        self._press(self.key_down)
