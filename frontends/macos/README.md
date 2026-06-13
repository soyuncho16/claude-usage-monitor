# macOS frontend

macOS 메뉴바 앱. 메뉴바에 `🟢 47% · 3h12m`(상태 이모지 + 5시간 사용률 + 리셋 카운트다운)을
표시하고, 클릭하면 5시간/7일/상태/지금 갱신 드롭다운을 연다. 단일 프로세스로,
공유 코어를 import해 백그라운드 스레드에서 폴링한다(10분 주기, 리셋 30분 전부터 1분).

## 개발 실행

```bash
pip install -r requirements.txt
python claude_usage_menubar.py
# repo 루트에서는: python frontends/macos/claude_usage_menubar.py (core를 자동 import)
```

## 번들 빌드

```bash
python setup.py py2app             # dist/Claude Usage Monitor.app
```

`~/.claude/.credentials.json`의 OAuth 토큰을 읽으므로 Claude Code 로그인이 되어 있어야 한다.

## 자동 시작 (선택)

`System Settings → General → Login Items`에 빌드된 .app을 추가한다.

## 검증 현황

> 작성자에게 Mac 실기가 없다. 표시·주기 로직(`usage_display.py`)과 코어는 Linux에서
> 단위 테스트로 검증되지만, rumps GUI 셸(`claude_usage_menubar.py`)의 실제 메뉴바
> 동작은 CI의 macOS 빌드(번들 생성)만 통과했을 뿐 **런타임 미검증 상태로 배포**된다.
> 이 한계를 릴리스 노트에 명시한다.
