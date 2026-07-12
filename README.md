# RS50 × Forza Horizon 6

Logitech G RS50 휠 + FH6 연동 유틸:

- **기능 A — 패들 오토↔매뉴얼 핸드오버**: 평소 텔레메트리 기반 자동 변속(키 인젝션),
  패들 조작 순간 수동 전환, 7초 무입력 또는 업패들 2초 홀드로 자동 복귀 (현대/제네시스 방식)
- **기능 B — RPM rev-light**: RS50 스트립(RGB 10개)을 텔레메트리로 직접 렌더링
  (F1 스타일: 초록→빨강→파랑 채움 + 풀 충전 시 보라 점멸)
- **웹 대시보드**: http://127.0.0.1:8777 — 기어/속도/RPM 바/모드/이벤트 로그 실시간

## 사용법

```powershell
pip install -r requirements.txt

# 게임 설정: HUD 및 게임플레이 > Data Out ON, IP 127.0.0.1, 포트 5607
#            변속 = 수동, 키보드 바인딩 시프트업 E / 시프트다운 Q 유지
python -m src.main --led     # 전체 기능
python -m src.main           # 오토시프트만
python tools\verify.py       # 하드웨어 검증 (게임 불필요, --visual: LED 스윕 포함)
```

## 아키텍처 핵심 (전부 실기 검증됨 — 이 표가 이 레포의 근거)

| 항목 | 확정 사실 |
|---|---|
| USB | `046d:c276` "RS50 Base for PlayStation/PC" |
| HID++ 라우팅 | 요청 short `0x10` → usage `0xFF43/0x701`, 응답은 **항상** very-long `0x12` ← usage `0x704` |
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
tools/verify.py     하드웨어 검증 스위트 (10항목)
tools/*.py          실측/진단 도구 (paddle_capture, hidpp_probe, led_* 등)
refs/               분석용 레퍼런스 클론 (git 미추적)
slot0_backup.json   슬롯 0 공장 패턴 백업 (초/노/빨 대칭)
```

## 주의/트러블슈팅

- **휠이 제멋대로 돌면**: 다른 프로그램이 SW_ID 0x0A~0x0E로 HID++를 쏘는지 의심 (본 레포는 0x03)
- LED가 안 바뀌면: G HUB LIGHTSYNC 효과를 아무거나 한 번 토글, 또는 `fast_updates = false`
- 슬롯 0을 공장 패턴으로 되돌리기: `slot0_backup.json` 참고 (초록2/노랑2/빨강2/노랑2/초록2, b5=2)
- 오버라이드 타임아웃/시프트 포인트/색상: `config.toml` 주석 참고
