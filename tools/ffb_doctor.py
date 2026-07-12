"""FFB 닥터 — 휠 FFB 설정 진단/복구/실주행 가이드.

usage:
    python tools/ffb_doctor.py            # 현재 설정 읽기 + 이상 징후 진단
    python tools/ffb_doctor.py --fix      # 이상 값을 권장값으로 복구 (항목별 y/n)
    python tools/ffb_doctor.py --guide    # 실주행 단계별 격리 시퀀스 (내일용)

배경: SW_ID 충돌 시기에 G HUB의 FFB 설정 상태가 오염됐을 수 있음.
설정은 휠 펌웨어에 저장되므로 HID++로 직접 읽고 쓸 수 있다 (mescon 스펙 §5).
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.hidpp import Rs50Hidpp, HidppError

# feature: (이름, 디코더, 인코더, 권장값표시, 이상판정)
def be16(p):
    return (p[0] << 8) | p[1]


SETTINGS = {
    0x8136: ("FFB 강도", lambda p: f"{be16(p)/8192:.1f} Nm (raw {be16(p):#06x})",
             lambda nm: bytes([int(nm*8191.875) >> 8, int(nm*8191.875) & 0xFF, 0]),
             "6.0 Nm 권장 (최대 8.0)",
             lambda p: be16(p)/8192 < 2.0 and "강도가 2Nm 미만 — '가볍다'의 직접 원인 후보"),
    0x8139: ("TRUEFORCE", lambda p: f"{be16(p)/655.35:.0f}% (raw {be16(p):#06x})",
             lambda pct: bytes([int(pct*655.35) >> 8, int(pct*655.35) & 0xFF, 0]),
             "30~50% 권장",
             lambda p: None),
    0x8133: ("댐핑", lambda p: f"{be16(p)/655.35:.0f}%",
             lambda pct: bytes([int(pct*655.35) >> 8, int(pct*655.35) & 0xFF, 0]),
             "10~30% 권장",
             lambda p: be16(p)/655.35 > 70 and "댐핑 과다 — 무겁고 둔한 느낌의 원인 후보"),
    0x8138: ("회전 범위", lambda p: f"{be16(p)}°",
             lambda deg: bytes([int(deg) >> 8, int(deg) & 0xFF, 0]),
             "900° 표준",
             lambda p: (be16(p) < 360 or be16(p) > 1440)
             and f"회전범위 {be16(p)}° — 게임 캘리브레이션과 불일치 시 쏠림처럼 느껴짐"),
    0x8140: ("FFB 필터", lambda p: f"level {p[2]} flags {p[0]:#04x}",
             None, "auto 또는 level 8~12", lambda p: None),
    0x8134: ("브레이크 포스", lambda p: f"{be16(p)/655.35:.0f}%",
             None, "-", lambda p: None),
}

SET_FN = {0x8136: 2, 0x8139: 3, 0x8133: 1, 0x8138: 2}
RECOMMENDED = {0x8136: 6.0, 0x8139: 40, 0x8133: 20, 0x8138: 900}


def read_all(dev):
    print(f"{'설정':<12} {'현재값':<28} 권장")
    print("-" * 64)
    anomalies = []
    for feat, (name, dec, _enc, rec, check) in SETTINGS.items():
        try:
            idx = dev.feature_index(feat)
            p = dev.call(idx, 1)
            warn = check(p)
            mark = "  <<< " + warn if warn else ""
            print(f"{name:<12} {dec(p):<28} {rec}{mark}")
            if warn:
                anomalies.append((feat, name, warn))
        except (HidppError, TimeoutError, KeyError) as e:
            print(f"{name:<12} 읽기 실패: {e}")
    # 프로필
    try:
        idx = dev.feature_index(0x8137)
        p = dev.call(idx, 1)
        mode = "데스크톱(호스트 제어)" if p[0] == 0 else f"온보드 {p[0]} (휠 자체 설정 사용!)"
        print(f"{'프로필':<12} {mode}")
        if p[0] != 0:
            anomalies.append((0x8137, "프로필",
                              "온보드 모드 — G HUB/호스트 설정이 무시될 수 있음"))
    except Exception as e:
        print(f"{'프로필':<12} 읽기 실패: {e}")
    return anomalies


def fix(dev):
    print("\n[FIX] 항목별 권장값 적용 (y = 적용, 그 외 = 건너뜀)")
    for feat, target in RECOMMENDED.items():
        name, dec, enc, rec, _ = SETTINGS[feat]
        idx = dev.feature_index(feat)
        before = dev.call(idx, 1)
        ans = input(f"  {name}: 현재 {dec(before)} -> {target} 적용? [y/N] ").strip().lower()
        if ans != "y":
            continue
        dev.call(idx, SET_FN[feat], enc(target))
        time.sleep(0.15)
        after = dev.call(idx, 1)
        if after == before and feat == 0x8139:
            # 실측(2026-07-13): TrueForce SET은 펌웨어가 조용히 거부하는 상태가 있음
            print("    !! 펌웨어가 쓰기를 무시함 — G HUB > RS50 > TRUEFORCE "
                  "슬라이더로 직접 설정하세요 (확실한 경로)")
        else:
            print(f"    적용됨 -> {dec(after)}")


GUIDE = """
=== 실주행 FFB 격리 시퀀스 (각 단계 30초~1분 주행 후 Enter) ===

[사전] 게임 설정 > 조작 > 고급 휠 설정 확인:
  - 포스 피드백 스케일 100 이상 / 자가 정렬 토크(SAT) 100 / 데드존 0-100 대칭
  - '진동 스케일'과 '포스 피드백'이 0으로 초기화되어 있지 않은지 (오염 흔적)

1단계: 우리 앱 완전 종료 + G HUB 실행 상태로 주행
  -> 여기서도 가볍거나 쏠리면: 원인은 우리 앱이 아님 (게임/GHUB/휠 설정)
2단계: (1이 정상일 때) 앱을 LED 없이 실행: python -m src.main
  -> 이상해지면: 키 인젝션/HID 읽기 경로 문제 (가능성 낮음, 보고 요망)
3단계: (2가 정상일 때) 전체 실행: start.bat
  -> 이상해지면: LED HID++ 트래픽이 원인 -> config update_hz를 6으로 낮춰 재시도
4단계: 쏠림(특히 우측)이 계속되면:
  - 정차 후 휠에서 손 떼고 스티어링이 스스로 한쪽으로 도는지 관찰
    돌면 = 센터 캘리브레이션 틀어짐 -> G HUB > 휠 설정 > 센터 재설정
    (또는 휠 베이스 OLED 메뉴 > Calibration)
  - 게임 내 데드존 좌우 비대칭 확인
  - TrueForce는 오디오 기반이라 좌우 오디오 밸런스가 틀어져 있으면 쏠림 유발
    -> 윈도우 사운드 밸런스 L/R 50:50 확인
5단계: 여전히 가볍다면 python tools/ffb_doctor.py 로 강도 재확인 후 --fix

각 단계 결과를 저한테 그대로 알려주시면 다음 수를 바로 드립니다.
"""


def main():
    if "--guide" in sys.argv:
        print(GUIDE)
        return
    dev = Rs50Hidpp()
    print("=== RS50 FFB 설정 진단 ===\n")
    anomalies = read_all(dev)
    print()
    if anomalies:
        print("이상 징후:")
        for _, name, warn in anomalies:
            print(f"  - [{name}] {warn}")
        print("\n복구: python tools/ffb_doctor.py --fix")
    else:
        print("휠 저장 설정은 정상 범위 — 원인은 게임 설정/캘리브레이션 쪽 가능성.")
        print("실주행 시퀀스: python tools/ffb_doctor.py --guide")
    if "--fix" in sys.argv:
        fix(dev)
    dev.close()


if __name__ == "__main__":
    main()
