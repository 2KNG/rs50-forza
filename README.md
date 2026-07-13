# RS50 × Forza Horizon 6

> **EN TL;DR** — Companion app for the Logitech G RS50 wheel + Forza Horizon 6 (PC):
> Hyundai/Genesis-style auto↔manual paddle handover (telemetry-driven autoshift via
> key injection, paddles hand over to manual, auto-resume by timeout/hold), direct
> RGB rev-strip control over reverse-engineered HID++ (coexists with G HUB), and a
> zero-dependency web dashboard (5 themes, analog/digital). Windows 10/11,
> Python 3.11+, `pip install -r requirements.txt`, run `start.bat`. Docs are Korean.

Logitech G RS50 휠 + FH6 연동 유틸:

- **기능 A — 패들 오토↔매뉴얼 핸드오버**: 평소 텔레메트리 기반 자동 변속(키 인젝션),
  패들 조작 순간 수동 전환, 7초 무입력 또는 업패들 2초 홀드로 자동 복귀 (현대/제네시스 방식)
- **기능 B — RPM rev-light**: RS50 스트립(RGB 10개)을 텔레메트리로 직접 렌더링
  (F1 스타일: 초록→빨강→파랑 채움 + 풀 충전 시 보라 점멸)
- **웹 대시보드**: http://127.0.0.1:8777 — 기어/속도/RPM 바/모드/이벤트 로그 실시간

## 게임할 때 (평소 루틴)

1. 게임 실행 (Data Out은 한 번 설정해두면 유지됨)
2. **`start.bat` 더블클릭** — 앱 기동 + 대시보드 자동 오픈, 이게 전부
3. 끝나면 그 콘솔에서 `Ctrl+C` (LED 정리 후 종료)

조작 요약:
| 조작 | 동작 |
|---|---|
| 그냥 주행 | 자동 변속 (0.88 업 / 0.35 다운, 코스팅 포함) |
| 패들 탭 | 수동 모드 (7초 무입력 시 자동 복귀) |
| 오른쪽 패들 2초 홀드 | 즉시 자동 복귀 |
| 왼쪽 패들 2초 홀드 | 후진 진입 (15km/h 이하) |

## 최초 1회 설정

```powershell
pip install -r requirements.txt
# 게임: HUD 및 게임플레이 > Data Out ON, IP 127.0.0.1, 포트 5607
#       변속 = 수동, 키보드 바인딩 시프트업 E / 시프트다운 Q 유지
python tools\verify.py       # 하드웨어 자가진단 (게임 불필요, --visual: LED 스윕)
```

## 아키텍처 핵심 (전부 실기 검증됨 — 이 표가 이 레포의 근거)

| 항목 | 확정 사실 |
|---|---|
| USB | `046d:c276` "RS50 Base for PlayStation/PC" |
| HID++ 라우팅 | 요청 short `0x10` → usage `0xFF43/0x701`. 응답: 베이스(dev 0xFF)=`0x12`←usage `0x704`, **서브디바이스(0x01/0x02/0x05)=`0x11`←usage `0x702`** |
| **SW_ID** | **`0x03` 고정. `0x0A~0x0E`는 G HUB 세션과 충돌 → FFB가 꼬여 휠이 제멋대로 회전** |
| LED 표시 | **표시는 슬롯 0만 렌더링** (슬롯 활성화 명령으로 표시 전환 불가). LED 사이 색은 펌웨어가 그라데이션 보간 |
| LED 갱신 | fn2 쓰기만으론 저장만 됨. 표시 반영 = fn2 + fn6-commit(`00 01 00 0A 00 0A`) + fn7 (3콜) |
| FFB 공존 | LED와 FFB 설정이 휠의 명령 처리기 공유 → **상시 전송 금지**. 변화시에만 전송(순항 0콜/s) |
| G HUB | **살려둘 것** (TrueForce가 G HUB 의존). 슬롯 0 "내용"을 갱신하는 방식이라 충돌 없음 |
| 패들 | 조이스틱 인터페이스(usage 0x01/0x04) byte 1: bit0=오른쪽(업), bit1=왼쪽(다운). read-only 병렬 관찰 |
| FH6 텔레메트리 | 324B 고정(FH4 레이아웃): rpm@16, max@8, idle@12, speed@256, gear@319(11=중립), accel@315. 메뉴에선 패킷 정지 |

## 구조

```
src/hidpp.py        HID++ 2.0 트랜스포트 (라우팅/SW_ID/에러/재시도)
src/telemetry.py    Data Out UDP 파서 (스레드)
src/paddle_watch.py 패들 관찰 스레드 (에지 + 홀드 감지)
src/autoshift.py    AUTO <-> MANUAL_OVERRIDE 상태머신
src/shifter.py      pydirectinput 키 인젝션
src/ledctl.py       rev-light 렌더러 (슬롯 0, 3콜 갱신, 프리셋/물결/점멸)
src/webui.py        웹 대시보드 (stdlib, 의존성 없음)
src/main.py         조립 + 이벤트 로그
tests/test_all.py   단위 테스트 18케이스 (python -m unittest tests.test_all)
tools/verify.py     하드웨어 검증 스위트 (10항목)
tools/ffb_doctor.py FFB 설정 진단/복구/가이드 (FFB_DEBUG.md 참고)
tools/recenter.py   센터 캘리브레이션 (우측 쏠림 해결, --set)
tools/settings_watch.py  설정 변경 실시간 감시 (SW_ID=0 브로드캐스트)
tools/soak.py       장시간 안정성 소크 테스트
tools/*.py          실측/진단 도구 (paddle_capture, hidpp_probe, led_* 등)
refs/               분석용 레퍼런스 클론 (git 미추적)
slot0_backup.json   슬롯 0 공장 패턴 백업 (초/노/빨 대칭)
```

## 크레딧 & 면책

- HID++/LED/캘리브레이션 프로토콜의 근간은 [mescon/logitech-trueforce-linux-driver](https://github.com/mescon/logitech-trueforce-linux-driver)의
  프로토콜 스펙 문서이며, 본 레포의 실기 검증으로 교차 확인/보완했습니다. 참고:
  [Juice-XIJ/forza_auto_gear](https://github.com/Juice-XIJ/forza_auto_gear),
  [GinoLin980/Forza-Horizon-realistic-gearbox](https://github.com/GinoLin980/Forza-Horizon-realistic-gearbox),
  [Mhytee/Trueforce-For-All](https://github.com/Mhytee/Trueforce-For-All)
- **역공학 기반 비공식 도구입니다.** Logitech/Playground Games와 무관하며, 사용에 따른
  책임은 사용자에게 있습니다 (MIT LICENSE). 휠 펌웨어에 설정을 쓰는 도구가 포함되어
  있으니 각 도구의 설명을 읽고 사용하세요.

## 주의/트러블슈팅

- **휠이 제멋대로 돌면**: 다른 프로그램이 SW_ID 0x0A~0x0E로 HID++를 쏘는지 의심 (본 레포는 0x03)
- LED가 안 바뀌면: G HUB LIGHTSYNC 효과를 아무거나 한 번 토글, 또는 `fast_updates = false`
- 슬롯 0을 공장 패턴으로 되돌리기: `slot0_backup.json` 참고 (초록2/노랑2/빨강2/노랑2/초록2, b5=2)
- 오버라이드 타임아웃/시프트 포인트/색상: `config.toml` 주석 참고
