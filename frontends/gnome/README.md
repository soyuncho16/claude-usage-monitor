# GNOME frontend

GNOME Shell 45+ 상단 패널 인디케이터 (GJS, ESM 확장 API). 패널에
`● 47% · 3h12m` 형태로 5시간 사용률과 리셋까지 남은 시간을 표시하고, 클릭하면
5시간/7일/상태 드롭다운을 연다.

## 설치

```bash
./install.sh
# 1) 셸 재시작 (X11: Alt+F2 → r, Wayland: 재로그인)
# 2) gnome-extensions enable claude-usage-monitor@soyuncho16.github.io
```

`install.sh`는 프론트엔드 파일과 공유 코어(`core/claude_usage_core.py`)를 확장
디렉토리로 복사한다. 인증·API는 코어가 전담하고, 이 확장은 코어를 spawn해
`state.json`을 읽기만 한다.

## 검증 현황

> GNOME 42–44 레거시 버전은 작성자 개인 repo에서 실기 검증되어 동작 중이다. 이
> 45+ 포팅은 ESM으로 구조가 달라 별도 코드이며, 작성자가 GNOME 42라 런타임은
> 정적 리뷰 + ESLint + GNOME 45+ 사용자/EGO 리뷰로 검증한다.
