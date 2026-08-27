# claude-usage-monitor

Claude 구독의 5시간/7일 사용량 한도를 GNOME 상단 패널에서 한눈에 본다. CPU 사용량을
보여주는 RunCat의 토큰 한도판.

`/usage`로 확인하던 "지금 몇 %, 리셋까지 몇 시간"을 터미널 대신 패널에서 상시 본다.

> 상태: 공유 코어 + GNOME 45+ 프론트엔드 완료(정적·CI 검증). 설계는
> [ARCHITECTURE.md](ARCHITECTURE.md).

## 동작 원리

GNOME 확장은 공유 코어(`core/claude_usage_core.py`)를 주기적으로 실행하고, 코어가 쓴
`state.json`을 읽어 표시한다. 코어는 `~/.claude/.credentials.json`의 OAuth 토큰으로
사용량 API 응답 **헤더**만 읽으므로 한도를 소비하지 않는다.

## 설치

GNOME Shell 45+ 전용. 설치법은 [frontends/gnome/README.md](frontends/gnome/README.md).

## 코어 단독 실행

```bash
python3 core/claude_usage_core.py              # 1회 폴링 → state.json
python3 core/claude_usage_core.py --dump-headers   # 응답 헤더 실측(토큰 미출력)
python3 -m unittest discover -s tests -v       # 전체 단위 테스트 (CI와 동일)
```

state.json 위치: `$XDG_CACHE_HOME/claude-usage/` (기본 `~/.cache/claude-usage/`).

## 라이선스

MIT — [LICENSE](LICENSE).
