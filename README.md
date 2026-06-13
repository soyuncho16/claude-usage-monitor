# claude-usage-monitor

Claude 구독의 5시간/7일 사용량 한도를 데스크톱에서 한눈에 — GNOME 패널, macOS 메뉴바,
Windows 트레이. CPU 사용량을 보여주는 RunCat의 토큰 한도판.

`/usage`로 확인하던 "지금 몇 %, 리셋까지 몇 시간"을 터미널 대신 패널에서 상시 본다.

> 상태: 공유 코어 + GNOME/macOS 프론트엔드 완료(정적·빌드·CI 검증), Windows 작업 예정.
> 설계는 [ARCHITECTURE.md](ARCHITECTURE.md).

## 동작 원리

프론트엔드는 공유 코어(`core/claude_usage_core.py`)를 통해 사용량을 얻는다 — 코어는
`~/.claude/.credentials.json`의 OAuth 토큰으로 사용량 API 응답 **헤더**만 읽으므로
한도를 소비하지 않는다. 코어를 부르는 방식은 두 가지이고, 인터페이스(state 계약)는 동일하다:

- **spawn 기반** (GNOME, 향후 Windows): 위젯이 코어를 주기적으로 실행하고, 코어가 쓴
  `state.json`을 읽어 표시한다.
- **in-process** (macOS): 단일 프로세스가 코어를 import해 백그라운드 스레드에서
  `poll_once_safe`를 호출한다(메뉴바를 멈추지 않음).

## 플랫폼별 현황

| 플랫폼 | 위젯 | 상태 |
| --- | --- | --- |
| Linux (GNOME 45+) | 상단 패널 인디케이터 | 동작 (정적·CI 검증) |
| macOS | 메뉴바 앱 (rumps + py2app) | 동작 (빌드·CI, 런타임 미검증) |
| Windows | 시스템 트레이 | 작업 예정 |

각 프론트엔드 설치법은 `frontends/<platform>/README.md` 참고.

## 코어 단독 실행

```bash
python3 core/claude_usage_core.py              # 1회 폴링 → state.json
python3 core/claude_usage_core.py --dump-headers   # 응답 헤더 실측(토큰 미출력)
python3 -m unittest discover -s tests -v       # 전체 단위 테스트 (CI와 동일)
```

state.json 위치: Linux `~/.cache/claude-usage/`, macOS `~/Library/Caches/claude-usage/`,
Windows `%LOCALAPPDATA%\claude-usage\`.

## 라이선스

MIT — [LICENSE](LICENSE).
