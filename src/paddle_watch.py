"""RS50 패들 입력 관찰 (read-only, 게임 입력과 병렬).

iface 0 (usage_page 0x0001 / usage 0x04, joystick) 입력 리포트를 논블로킹으로
읽어 패들 비트 변화를 감지한다. 게임에는 원래 입력이 그대로 전달되므로
가로채기/지연 없음 (Windows HID 공유 read).

휠 분리/재열거 시 스레드가 죽지 않고 1초 간격으로 재연결을 시도한다.
"""
import threading
import time

import hid

VID, PID = 0x046D, 0xC276


class PaddleWatcher(threading.Thread):
    def __init__(self, byte_up, bit_up, byte_down, bit_down,
                 on_paddle=None, on_hold=None, hold_s=2.0, log=print):
        """on_paddle(direction): 눌림 에지 콜백. on_hold(direction): hold_s 이상
        연속 홀드 시 1회 콜백 (현대/제네시스식 '+패들 홀드 -> D 복귀'용)."""
        super().__init__(daemon=True, name="paddle")
        self.byte_up, self.bit_up = byte_up, bit_up
        self.byte_down, self.bit_down = byte_down, bit_down
        self.on_paddle = on_paddle
        self.on_hold = on_hold
        self.hold_s = hold_s
        self.log = log
        self.last_paddle_time = 0.0
        self._stop = threading.Event()
        # 시작 전에 열어서 휠 부재를 조용히 넘기지 않고 즉시 실패시킴
        self._h = self._open_joystick()

    def stop(self):
        self._stop.set()

    @staticmethod
    def _open_joystick():
        for d in hid.enumerate(VID, PID):
            if d.get("usage_page") == 0x0001 and d.get("usage") == 0x04:
                h = hid.device()
                h.open_path(d["path"])
                h.set_nonblocking(True)
                return h
        raise RuntimeError("RS50 조이스틱 인터페이스 미발견 — 휠 연결 확인")

    def _reconnect(self):
        """휠 분리/재열거 시 재연결 (성공까지 1초 간격 재시도)."""
        try:
            self._h.close()
        except Exception:
            pass
        self._h = None
        while not self._stop.is_set():
            try:
                self._h = self._open_joystick()
                self.log("[paddle] 휠 재연결됨")
                return True
            except Exception:
                self._stop.wait(1.0)
        return False

    def run(self):
        prev_up = prev_down = False
        since = {"up": None, "down": None}      # 눌림 시작 시각
        fired = {"up": False, "down": False}    # 홀드 콜백 발화 여부
        while not self._stop.is_set():
            now = time.time()
            try:
                data = bytes(self._h.read(64))
            except (OSError, ValueError) as e:
                self.log(f"[paddle] 읽기 오류({e}) — 재연결 시도")
                if not self._reconnect():
                    break
                prev_up = prev_down = False
                since = {"up": None, "down": None}
                continue
            if data:
                need = max(self.byte_up, self.byte_down)
                if len(data) <= need:
                    continue
                up = bool(data[self.byte_up] & (1 << self.bit_up))
                down = bool(data[self.byte_down] & (1 << self.bit_down))
                try:
                    for name, cur, prev in (("up", up, prev_up),
                                            ("down", down, prev_down)):
                        if cur and not prev:
                            self.last_paddle_time = now
                            since[name] = now
                            fired[name] = False
                            if self.on_paddle:
                                self.on_paddle(name)
                        if not cur:
                            since[name] = None
                            fired[name] = False
                except Exception as e:
                    self.log(f"[paddle] 콜백 오류(계속 진행): {e}")
                prev_up, prev_down = up, down
            else:
                time.sleep(0.001)
            # 홀드 판정 (리포트 유무와 무관하게 마지막 상태 기준)
            for name in ("up", "down"):
                if (since[name] is not None and not fired[name]
                        and now - since[name] >= self.hold_s):
                    fired[name] = True
                    try:
                        if self.on_hold:
                            self.on_hold(name)
                    except Exception as e:
                        self.log(f"[paddle] 홀드 콜백 오류: {e}")
        if self._h:
            self._h.close()
