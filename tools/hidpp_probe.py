"""RS50 HID++ 2.0 feature 테이블 덤프 (읽기 전용).

확인된 라우팅:
  - 요청: short 리포트 0x10 (7B) -> usage_page 0xFF43 / usage 0x701 컬렉션
  - 응답: very-long 리포트 0x12 (64B) <- usage 0x704 컬렉션

IRoot(0x0000) / IFeatureSet(0x0001)만 사용. set 계열 명령은 보내지 않는다.

usage: python tools/hidpp_probe.py
"""
import sys
import time

import hid

VID, PID = 0x046D, 0xC276
DEV_IDX = 0xFF
SW_ID = 0x03  # 0x0A-0x0E는 G HUB 세션과 충돌 (FFB 오염) — src.hidpp와 동일 값

KNOWN = {
    0x0000: "IRoot", 0x0001: "IFeatureSet", 0x0002: "IFeatureInfo",
    0x0003: "DeviceInformation", 0x0005: "DeviceTypeName",
    0x0007: "DeviceFriendlyName", 0x0020: "ConfigChange",
    0x00C2: "DFUControl", 0x00C3: "DFUControlSigned", 0x00D0: "DFU",
    0x1000: "BatteryStatus", 0x1300: "LedControl",
    0x1602: "PasswordAuth", 0x1801: "ManufacturingMode",
    0x1802: "DeviceReset", 0x1805: "OOBState", 0x1806: "ConfigDeviceProps",
    0x1830: "PowerModes", 0x18A1: "LEDTest", 0x1E00: "EnableHiddenFeatures",
    0x1E02: "ManageDeactivatableFeatures", 0x1E22: "SPIDirectAccess",
    0x1EB0: "TdeAccessToNvm", 0x1F1F: "FirmwareProperties",
    0x1B00: "ReprogControlsV0", 0x1B04: "ReprogControlsV4",
    0x2201: "AdjustableDpi", 0x40A2: "FnInversion",
    0x8010: "GamingGKeys", 0x8020: "GamingMKeys", 0x8030: "MR",
    0x8040: "BrightnessControl", 0x8060: "ReportRate",
    0x8061: "ExtendedAdjustableReportRate",
    0x8070: "ColorLedEffects", 0x8071: "RGBEffects",
    0x8080: "PerKeyLighting", 0x8081: "PerKeyLightingV2",
    0x8090: "ModeStatus", 0x80A0: "AxisResponseCurve", 0x80A1: "AdcMeasurement",
    0x80D0: "CombinedPedals", 0x8100: "OnboardProfiles",
    0x8110: "MouseButtonSpy", 0x8123: "ForceFeedback",
    0x8134: "BrakeForce",
}

LED_CANDIDATES = (0x1300, 0x8040, 0x8070, 0x8071, 0x8080, 0x8081, 0x18A1)


class Hidpp:
    def __init__(self):
        self.h_tx = self._open(0x701)   # short 요청 송신
        self.h_rx = self._open(0x704)   # very-long 응답 수신
        self.h_rx.set_nonblocking(True)

    @staticmethod
    def _open(usage):
        for d in hid.enumerate(VID, PID):
            if d.get("usage_page") == 0xFF43 and d.get("usage") == usage:
                h = hid.device()
                h.open_path(d["path"])
                return h
        print(f"usage 0x{usage:03X} 컬렉션 미발견"); sys.exit(1)

    def call(self, feat_idx, func, params=b"", retries=3):
        func_sw = ((func & 0x0F) << 4) | SW_ID
        req = bytes([0x10, DEV_IDX, feat_idx, func_sw]) + params
        req = req + b"\x00" * (7 - len(req))
        for _ in range(retries):
            self.h_tx.write(req)
            t0 = time.time()
            while time.time() - t0 < 1.0:
                resp = bytes(self.h_rx.read(64))
                if not resp:
                    time.sleep(0.002)
                    continue
                if resp[1] != DEV_IDX:
                    continue
                # HID++ 2.0 에러 프레임: featIdx 자리가 0xFF
                if resp[2] == 0xFF and resp[3] == feat_idx and resp[4] == func_sw:
                    return None, resp[5]
                if resp[2] == feat_idx and resp[3] == func_sw:
                    return resp[4:], None
        return None, "timeout"

    def close(self):
        self.h_tx.close()
        self.h_rx.close()


def main():
    dev = Hidpp()

    p, err = dev.call(0x00, 0, bytes([0x00, 0x01]))  # IRoot.getFeature(IFeatureSet)
    if err is not None:
        print(f"IRoot.getFeature 실패: {err}"); sys.exit(1)
    ifs_idx = p[0]

    p, err = dev.call(ifs_idx, 0)  # IFeatureSet.getCount
    if err is not None:
        print(f"getCount 실패: {err}"); sys.exit(1)
    count = p[0]
    print(f"feature 개수 = {count} (IFeatureSet idx={ifs_idx})\n")
    print(f"{'idx':>3}  {'featID':>6}  {'type':>4}  {'ver':>3}  name")

    found = {}
    for i in range(0, count + 1):
        p, err = dev.call(ifs_idx, 1, bytes([i]))  # getFeatureId(i)
        if err is not None:
            print(f"{i:>3}  (에러 {err})")
            continue
        feat_id = (p[0] << 8) | p[1]
        ftype, fver = p[2], p[3]
        name = KNOWN.get(feat_id, "?")
        tag = "  <<< LED 후보!" if feat_id in LED_CANDIDATES else ""
        print(f"{i:>3}  0x{feat_id:04X}  0x{ftype:02X}  {fver:>3}  {name}{tag}")
        found[feat_id] = i

    # 디바이스 이름 확인 (0x0005 DeviceTypeName, 읽기 전용)
    if 0x0005 in found:
        idx = found[0x0005]
        p, err = dev.call(idx, 0)  # getDeviceNameCount
        if err is None:
            n = p[0]
            name_bytes = b""
            off = 0
            while off < n:
                p, err = dev.call(idx, 1, bytes([off]))  # getDeviceName(offset)
                if err is not None:
                    break
                name_bytes += p
                off += len(p)
            print(f"\n장치 이름: {name_bytes[:n].decode(errors='replace')}")

    dev.close()

    leds = [f for f in LED_CANDIDATES if f in found]
    print()
    if leds:
        print("LED 관련 feature:", ", ".join(f"0x{f:04X}(idx {found[f]})" for f in leds))
    else:
        print("표준 LED feature 없음 -> 비표준 경로(G HUB 캡처) 필요")


if __name__ == "__main__":
    main()
