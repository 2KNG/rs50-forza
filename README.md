# RS50 × Forza Horizon 6 — 드리프트 텔레메트리 대시보드

> **EN TL;DR** — Zero-dependency telemetry dashboard for Forza Horizon (FH4-layout
> UDP "Data Out") built for a 4K triple-monitor drift setup: `/left` shows driving
> essentials (GT7-style tacho, analog speedo, G-G meter), `/right` is all drift
> (drift-angle dial, lat-G bar, tire temps/slip, driving line map, input trace,
> scoreboard). 6 themes, per-monitor toggles (fonts, flame-style rev bar, dual rev
> bars), full-channel 60 fps interpolation. Pure Python stdlib server + vanilla JS.
> Windows 10/11, Python 3.11+. Run `start.bat`. Docs are Korean.
> The repo also contains the first public protocol-level documentation of the
> Logitech RS50's HID++ LED/FFB pipeline — see [FFB_DEBUG.md](FFB_DEBUG.md).

트리플 모니터(좌/중앙 게임/우)용 **순수 텔레메트리 대시보드**입니다.
게임 옆 모니터 2장을 실차 계기판으로 만듭니다. 휠/게임에는 아무것도 쓰지 않고
UDP 수신만 하므로 조작감·FFB에 영향이 0입니다.

| 페이지 | 내용 |
|---|---|
| `http://127.0.0.1:8777/left` | 주행 필수: GT7식 타코(% REDLINE + 기어), 아날로그 속도계(AVG/MAX), G-G 미터 |
| `http://127.0.0.1:8777/right` | 드리프트 전부: 각도 다이얼+피크, 횡G 바, 타이어 온도/슬립/서스 4륜, 주행라인 맵, 입력 트레이스(스로틀/브레이크/조향/핸드브레이크), 스코어보드(피크각·최대G·유지시간·차량 클래스/PI) |
| `http://127.0.0.1:8777/` | 단일 화면 종합판 |

## 시작하기

```powershell
# 최초 1회
pip install -r requirements.txt
# 게임 설정: HUD 및 게임플레이 > Data Out ON, IP 127.0.0.1, 포트 5607

# 평소: 이거 하나
start.bat        # 앱 기동 + 양쪽 모니터에 대시보드 자동 배치
```

rev 바는 **바깥(모니터 끝) → 중앙(게임)** 방향으로 차오르는 미러 구조라
게임 화면을 중심으로 좌우가 대칭으로 감쌉니다.

## 화면 커스터마이즈 (우상단 스위처, 모니터별로 따로 기억됨)

| 토글 | 옵션 | 설명 |
|---|---|---|
| 테마 | PIT · **GT** · F1 · RETRO · OLED · NEON | GT = GT7 럭셔리 클러스터(3계층 눈금, 해치 레드존, GEAR 디스크, AVG/MAX) |
| 숫자 폰트 | AA · DIN · 01 | DIN = Bahnschrift(실차 계기판 표준 서체), 01 = 모노스페이스 |
| rev 바 위치 | BAR ▲ · BAR ▲▼ | ▲▼ = 화면 하단에도 rev 바 추가 |
| rev 바 스타일 | SEG · FIRE | FIRE = 일렁이는 화염 실루엣 (프리셋 그라데이션) |
| 표시 모드 | DIG · ANA | 디지털 숫자판 ↔ 아날로그 게이지 |

오버레브(변속 시점) 도달 시 전체 스트립이 보라색으로 8Hz 점멸하고
화면 테두리가 함께 번쩍입니다.

URL 파라미터로도 강제 가능: `/left?th=gt&fn=din&bar=both&fx=flame&dsp=analog`
(순서대로 테마/폰트/바 위치/바 스타일/표시 모드 — 스크린샷·검증용)

## 왜 부드러운가

- 수신은 150ms 폴링이지만 표시는 **전 채널 지수 스무딩 + 60fps 렌더**입니다.
  RPM/속도만이 아니라 G값·드리프트각·조향·핸드브레이크·타이어 온도/슬립/서스·
  맵 좌표까지 전부 보간됩니다.
- 채널별 반응속도 차등: 조향·페달은 빠릿하게(rate 18), G/좌표는 중간(12),
  타이어 온도는 묵직하게(4) — 뭉개짐 없이 부드럽기만 합니다.
- 백그라운드 탭 폴백, NaN/Infinity 새니타이즈, 음수 dt 클램프 포함.

## 설정 (`config.toml`)

| 섹션 | 키 | 의미 |
|---|---|---|
| `[telemetry]` | `port` | 게임 Data Out 포트 (기본 5607) |
| `[web]` | `port`, `host` | 대시보드 주소 (기본 127.0.0.1:8777, 폰 접속은 host="0.0.0.0") |
| `[led]` | `start_ratio` | rev 바 점등 시작 rpm 비율 (기본 0.5) |
| `[led]` | `blink_ratio` | 오버레브 점멸 시작 비율 = 권장 변속 시점 (기본 0.88) |
| `[led]` | `preset` | rev 바 색 프리셋 (`f1` = 초록→빨강→파랑, 보라 점멸) |

## 개발자용

```powershell
# 본 인스턴스(8777) 옆에서 충돌 없이 개발 인스턴스(8778/UDP 5608) 실행
$env:RS50_CONFIG="config.dev.toml"; python -m src.main --monitor
$env:RS50_CONFIG="config.dev.toml"; python tools\demo_telemetry.py 30   # 가짜 드리프트 주행

python tests\test_all.py                                    # 단위 테스트
# 스크린샷 검증 (실제 사이드 모니터와 동일한 2560x1440 CSS 뷰포트)
msedge --headless=new --disable-gpu --window-size=2560,1440 `
  --virtual-time-budget=8000 --screenshot=out.png "http://127.0.0.1:8778/left?th=gt"
```

```
src/main.py         엔트리 (--monitor = 기본 모드, 휠·게임 완전 무접촉)
src/telemetry.py    Data Out UDP 파서 — 크기로 포맷 자동판별(232/311/324B), 4륜 타이어/좌표 포함
src/webui.py        대시보드 전체 (stdlib http.server + vanilla JS, 외부 의존성·리소스 0)
config.toml         본 설정 / config.dev.toml 개발용
tools/demo_telemetry.py  게임 없이 개발용 합성 드리프트 텔레메트리
tools/open_dashboards.ps1 모니터 자동 감지 + Edge 앱창 좌우 배치
tests/test_all.py   단위 테스트
```

## 연구 기록 — RS50 하드웨어 제어의 은퇴 (읽을 가치 있음)

이 레포는 원래 ① 패들 오토↔매뉴얼 핸드오버(텔레메트리 오토시프트 + 키 인젝션)와
② RS50 RGB 스트립 직접 제어(HID++ 역공학)로 시작했고, **둘 다 완성했지만 은퇴**시켰습니다.

- RS50는 FFB와 LED/입력 경로가 USB 파이프를 공유합니다. LED 전송(어떤 빈도든),
  패들 HID 병렬 읽기, 키보드 인젝션 **모두가 FH6의 FFB/조작감을 오염**시킴을
  격리 실험으로 확정했습니다 (모니터 전용 모드 = 완전 정상).
- 그 과정에서 얻은 **RS50 HID++ 프로토콜 전체 지도**(SW_ID 충돌 규칙, LED 슬롯 0
  전용 표시, 3콜 갱신 시퀀스, 서브디바이스 라우팅, 센터 캘리브레이션)는 세계 최초의
  공개 기록입니다 → **[FFB_DEBUG.md](FFB_DEBUG.md)**
- 구현체는 전부 남아 있습니다: `src/hidpp.py` `src/ledctl.py` `src/autoshift.py`
  `src/paddle_watch.py` `src/shifter.py`, 진단 도구 `tools/verify.py`
  `tools/ffb_doctor.py` `tools/recenter.py` 등. LED가 FFB와 무관한 다른 휠이나
  향후 펌웨어에서는 그대로 재사용 가능합니다.
- 인젝션의 이론적 우회로는 ViGEm 가상 컨트롤러 에뮬레이션(미검증, 미래 과제).

## 크레딧 & 면책

- HID++ 프로토콜 근간: [mescon/logitech-trueforce-linux-driver](https://github.com/mescon/logitech-trueforce-linux-driver)
  (본 레포 실기 검증으로 교차 확인/보완). 참고:
  [Juice-XIJ/forza_auto_gear](https://github.com/Juice-XIJ/forza_auto_gear),
  [GinoLin980/Forza-Horizon-realistic-gearbox](https://github.com/GinoLin980/Forza-Horizon-realistic-gearbox)
- 역공학 기반 비공식 도구입니다. Logitech/Playground Games와 무관하며 사용 책임은
  사용자에게 있습니다 (MIT LICENSE). 휠 펌웨어에 쓰는 도구가 일부 포함되어 있으니
  각 도구의 설명을 읽고 사용하세요.
