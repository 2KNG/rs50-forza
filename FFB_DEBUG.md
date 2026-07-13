# FFB 디버깅 플레이북 — 무감각/가벼움 + 우측 쏠림

> 2026-07-13 원격 진단 + 커뮤니티/문서 조사(2-에이전트) 종합.
> **정정**: 처음엔 TrueForce 0%를 주범으로 봤으나, **FH6는 RS50 TrueForce를
> 네이티브 지원하지 않음** (TF4ALL SimHub 플러그인 전용) → FH6 체감과 무관.

## 원격으로 이미 조치한 것 (휠 펌웨어에 저장됨)

- 프로필: 온보드 1 → **데스크톱** (호스트 설정이 먹히는 모드)
- FFB 강도: 5.0 → **8.0 Nm** (커뮤니티 기준선 = 베이스 최대, 실제 세기는 게임 내 스케일로 조절)
- 댐핑 0% / 필터 11(auto) = 정상 확인

## 유력 원인 순위 (조사 결과)

| 증상 | 1순위 | 2순위 |
|---|---|---|
| 가벼움/무감각 | **FH6 Device-1 라우팅 버그** (FFB가 다른 USB 장치로 감) | Forza 휠 프로파일 파일 오염, 게임 내 FFB 스케일 |
| 상시 우측 쏠림 | **센터 캘리브레이션 드리프트** (RS50 공장 오프셋 ~1.5° 보고 다수) | FH6 강제 센터스프링 버그 |
| 조향 방향으로 빨림 | 게임 내 "Invert Force Feedback" 토글 | - |

## 내일 시퀀스 (순서대로)

**0. G HUB에서 (게임 전, 5분)**
- ~~펌웨어 업데이트~~ → **확인 완료: U1 65.04.0039 = 165.4.39 = 최신 (2026-05),
  2025-12 FFB사망 픽스 포함** — 업데이트 불필요
- 설정 확인: 강도 최대(제가 8.0 설정함), 댐퍼 0, 필터 5~11, **회전 범위 900°**
  (참고: G HUB가 실행 중이면 이 값들은 G HUB 저장 프로필이 최종 권위 —
   실측으로 데스크톱 전환 직후 G HUB가 720°/브레이크20%를 재적용하는 것 확인함.
   반드시 G HUB UI에서 맞출 것)
- **쏠림 해결 (2가지 방법 중 택1)**:
  ① G HUB > 장치 설정(톱니) > **Calibrate** — 휠 정중앙 잡고 실행
  ② 우리 도구: **`python tools\recenter.py --set`** (휠 정중앙 잡고) — 서브디바이스
    통신 검증 완료, 드리프트를 counts 단위로 기록/추적함. 이후 `recenter.py`만
    실행하면 드리프트 수치 확인 가능
- 끝나면 **베이스 전원 재인입** (설정이 재부팅 후에야 반영되는 사례 다수)

**1. Device 1 확인 (가벼움의 핵심) — 사전 검증됨: 이 PC의 DirectInput 게임
컨트롤러는 RS50 하나뿐** (2026-07-13 스캔 — 패드/조이스틱 없음, Razer 키/마우스는
게임 컨트롤러로 안 잡힘). 그래도 게임에서 스티어링 바인딩 화면에 "Device 1"로
표시되는지 한 번만 확인. HidHide/DSX/SimHub 미설치 확인됨 (FFB 킬러 부재).

**2. 게임 내 DD 권장값 (커뮤니티 합의값)**
- FFB Scale **0.75~0.8** (그래도 가벼우면 1.5까지) / Center Spring **0** / Damper 0~0.2
- Mechanical Trail 1.0 / **Min Force 0** (5%만 줘도 RS50은 발진함) / Load Sens 0.5
- Road Feel 0.4 / Off-Road 0.2 / Sensitivity 0.5 / Linearity 40~50
- 데드존: inside **0** / outside **100** / 스티어링 모드 Normal (Simulation은 휠에서 과민)

**3. 주행 테스트 (앱 없이)** → 정상이면 4로, 이상 시 증상별:
- 여전히 가벼움 → Forza 프로파일 오염 의심 (스팀판 실경로 확인됨):
  `%LOCALAPPDATA%\ForzaHorizon6\LocalStorage_Shared\InputTranslationManager_901F1DF905BC3`
  폴더를 백업 후 삭제, **휠 켠 채로** 게임 재시작, 프로파일 재작성
- 쏠림이 남음 → 인카 상태에서 **휠 USB 뽑았다 재연결** (강제 센터스프링 버그 해제)
- 조향 방향으로 빨려들어감 → Advanced Controls > **Invert Force Feedback** 토글

**4. 우리 앱 격리**: `python -m src.main` (LED 없이) → `start.bat` (전체)
- 전체에서만 이상 → config `update_hz = 6`

**5. 그래도 남으면**: 전원 옵션 > USB 선택적 절전 끄기 / HidHide·DSX 실행 여부 확인
(둘 다 RS50 FFB를 죽인 사례 보고됨)

## 참고
- 진단 도구: `python tools\ffb_doctor.py` (읽기) / `--fix` / `--guide`
- 센터: `python tools\recenter.py` (드리프트 확인) / `--set` (정중앙 잡고 저장)
- 설정 감시: `python tools\settings_watch.py 60` — 뭔가가 설정을 몰래 바꿀 때 실시간 포착
- 주의: 게임을 **휠 없이 실행하면 휠 프로파일이 조용히 초기화**됨 — 항상 휠 먼저

## 선택지: FH6에서 TrueForce 살리기 (TF4ALL) — 원하면 나중에

FH6는 네이티브 TrueForce가 없지만 **TF4ALL**(SimHub 플러그인)로 추가 가능:
- 설치: SimHub + TrueforceForAll-Setup-**0.1.25**.exe (v0.2.0 베타는 자체 rev-light가
  우리 LED와 충돌하므로 금지)
- 설정: FH6 Data Out → 127.0.0.1:**5300** (TF4ALL), TF4ALL의 Data Relay로
  127.0.0.1:5607(우리 앱) 전달 — 우리 앱 무수정으로 공존
- **G HUB는 세션 내내 완전 종료** 필수 (네이티브 FFB는 G HUB 없어도 동작)
- TF4ALL은 MI_02(0xFFFD)만 독점 — 우리 앱(MI_01)과 인터페이스 분리, 공존 전망.
  단 "커스텀 HID++ LED 앱과 동시 구동" 선례는 없음 — 우리가 첫 사례, 단계적 테스트 필요
- 주의: TrueForce 강도는 물리 다이얼이 아니라 플러그인 내 Master Gain으로 조절
