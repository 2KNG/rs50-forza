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
             "8.0 Nm (베이스 최대, 세기는 게임 스케일로)",
             lambda p: be16(p)/8192 < 4.0 and "강도 낮음 — '가볍다'에 기여 가능"),
    0x8139: ("TRUEFORCE", lambda p: f"{be16(p)/655.35:.0f}% (raw {be16(p):#06x})",
             lambda pct: bytes([int(pct*655.35) >> 8, int(pct*655.35) & 0xFF, 0]),
             "FH6 네이티브 미지원 — 체감 무관 (TF4ALL 전용)",
             lambda p: None),
    0x8133: ("댐핑", lambda p: f"{be16(p)/655.35:.0f}%",
             lambda pct: bytes([int(pct*655.35) >> 8, int(pct*655.35) & 0xFF, 0]),
             "0% (2026-07-13 실측 정상값, FFB_DEBUG 기준)",
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
RECOMMENDED = {0x8136: 8.0, 0x8133: 0, 0x8138: 900}


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
        if after == before:
            # 실측(2026-07-13): 일부 설정은 펌웨어가 쓰기를 조용히 무시함
            print(f"    !! 펌웨어가 쓰기를 무시함 — G HUB의 {name} 슬라이더로 "
                  "직접 설정하세요")
        else:
            print(f"    적용됨 -> {dec(after)}")


GUIDE = """
=== 실주행 FFB 시퀀스 (상세는 FFB_DEBUG.md) ===

0. G HUB: 펌웨어 업데이트 확인(2025-12에 FFB사망 픽스) + Calibrate(정중앙 잡고)
   -> 베이스 전원 재인입
1. 다른 USB 입력장치 전부 분리, 게임에서 스티어링 리바인드 -> "Device 1" 확인
   (FH6는 Device 1에만 FFB를 보냄 — '가벼움'의 1순위 원인)
2. 게임 내: FFB Scale 0.75-0.8 / Center Spring 0 / Min Force 0 /
   데드존 0/100 / Linearity 40-50 / 모드 Normal
3. 앱 없이 주행 테스트
   - 가벼움 지속 -> Forza InputTranslationManager 프로파일 삭제 후 재작성
   - 쏠림 지속 -> 인카 상태 USB 재연결 (센터스프링 버그)
   - 조향 방향으로 빨림 -> Invert Force Feedback 토글
4. python -m src.main (LED 없이) -> start.bat (전체) 순서로 격리
5. 남으면: USB 선택적 절전 OFF, HidHide/DSX 확인

각 단계 결과를 알려주면 다음 수를 바로 드립니다.
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
