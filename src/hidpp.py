"""RS50 HID++ 2.0 트랜스포트.

확인된 라우팅 (2026-07-11 실측):
  - 요청: short 0x10 (7B) -> usage_page 0xFF43 / usage 0x701
  - 응답: very-long 0x12 (64B) <- usage 0x704
  - long 0x11 요청이 필요한 경우(파라미터 4B 초과) 0x702 경유 시도

G HUB 실행 중에도 병렬 오픈/통신 가능 (Windows HID 공유 모드).
"""
import time

import hid

VID, PID = 0x046D, 0xC276
DEV_IDX = 0xFF
# SW_ID 선택 주의: G HUB가 0x0A-0x0E를 병렬 세션으로 사용(문서 확인) — 겹치면
# G HUB가 우리 응답을 자기 것으로 오인해 FFB 설정이 꼬임(휠이 제멋대로 회전).
# 0x01은 페달 MCU가 무시, 0x00은 이벤트용, 0x0F는 DFU -> 0x03 사용.
SW_ID = 0x03


class HidppError(Exception):
    def __init__(self, code):
        super().__init__(f"HID++ error {code}")
        self.code = code


class Rs50Hidpp:
    def __init__(self):
        self.h_short = self._open(0x701)
        self.h_long = self._open(0x702)
        self.h_vlong = self._open(0x704)
        self.h_vlong.set_nonblocking(True)
        self._feat_cache = {}

    @staticmethod
    def _open(usage):
        for d in hid.enumerate(VID, PID):
            if d.get("usage_page") == 0xFF43 and d.get("usage") == usage:
                h = hid.device()
                h.open_path(d["path"])
                return h
        raise RuntimeError(f"RS50 HID++ 컬렉션(usage=0x{usage:03X}) 미발견 — 휠 연결 확인")

    def close(self):
        for h in (self.h_short, self.h_long, self.h_vlong):
            h.close()

    def call(self, feat_idx, func, params=b"", timeout=1.0, retries=3):
        """HID++ 2.0 호출. 파라미터 길이에 따라 short/long/very-long 자동 선택."""
        func_sw = ((func & 0x0F) << 4) | SW_ID
        head = bytes([DEV_IDX, feat_idx, func_sw])
        if len(params) <= 3:
            req, h_tx = bytes([0x10]) + head + params, self.h_short
            req += b"\x00" * (7 - len(req))
        elif len(params) <= 16:
            req, h_tx = bytes([0x11]) + head + params, self.h_long
            req += b"\x00" * (20 - len(req))
        else:
            req, h_tx = bytes([0x12]) + head + params, self.h_vlong
            req += b"\x00" * (64 - len(req))

        # 일부 펌웨어는 응답의 SW_ID 니블을 0으로 지움(드라이버 문서) ->
        # 그 경우 function 니블만으로 매칭 허용
        fn_only = func_sw & 0xF0
        def match_fs(b):
            return b == func_sw or b == fn_only

        last_err = "timeout"
        for _ in range(retries):
            h_tx.write(req)
            t0 = time.time()
            while time.time() - t0 < timeout:
                resp = bytes(self.h_vlong.read(64))
                if not resp:
                    time.sleep(0.002)
                    continue
                if resp[1] != DEV_IDX:
                    continue
                if resp[2] == 0xFF and resp[3] == feat_idx and match_fs(resp[4]):
                    last_err = resp[5]
                    raise HidppError(resp[5])
                if resp[2] == feat_idx and match_fs(resp[3]):
                    return resp[4:]
        raise TimeoutError(f"HID++ 응답 없음 (feat_idx={feat_idx}, func={func}, {last_err})")

    def feature_index(self, feat_id):
        """IRoot.getFeature: feature ID -> index (캐시)."""
        if feat_id not in self._feat_cache:
            p = self.call(0x00, 0, bytes([feat_id >> 8, feat_id & 0xFF]))
            idx = p[0]
            if idx == 0:
                raise KeyError(f"feature 0x{feat_id:04X} 미지원")
            self._feat_cache[feat_id] = idx
        return self._feat_cache[feat_id]
