# Architecture

크로스플랫폼 단일 원칙: **공유 코어 하나 + 플랫폼별 얇은 프론트엔드.** 둘은
`state.json` 파일 하나로만 통신한다.

```text
core/claude_usage_core.py   ← 데이터: 인증·API·헤더파싱·상태쓰기 (Python 표준 라이브러리)
        │  writes
        ▼
  <cache>/claude-usage/state.json   ← 유일한 인터페이스
        ▲  reads + spawns core
        │
frontends/{gnome,macos,windows}/   ← 표시: 각 플랫폼 네이티브 위젯
```

모든 프론트엔드는 코어 스크립트를 spawn하고 state.json을 읽기만 한다. 인증·HTTP는
어느 프론트엔드도 모른다.

---

# 공유 코어

`python3 core/claude_usage_core.py` 1회 실행 → `~/.claude/.credentials.json`의 OAuth
토큰으로 `POST /v1/messages`(max_tokens 1) 호출 → 응답 헤더
`anthropic-ratelimit-unified-*` 파싱 → state.json 원자적 쓰기.

폴링은 한도를 소비하지 않는다 — 사용량은 응답 헤더에 실려오고, 2회 연속 호출에서
utilization이 변하지 않음을 실측 확인했다.

OS별로 다른 것은 캐시 경로뿐(`_cache_dir`): Linux `~/.cache`(XDG), macOS
`~/Library/Caches`, Windows `%LOCALAPPDATA%`. 자격증명 경로는 세 OS 공통(`~/.claude`).

## state.json 계약

```json
{
  "ok": true,
  "fetched_at": 1749720000,
  "five_h":  { "utilization": 47, "resets_at": 1749730000 },
  "seven_d": { "utilization": 12, "resets_at": null },
  "status": "allowed",
  "error": null
}
```

실패 시 `ok:false` + `error:{type, message}` (`type ∈ no_creds | auth_expired |
network | rate_limited | parse`), 직전 성공 값은 보존.

---

# 프론트엔드 현황과 검증

| 프론트엔드 | 기술 | 상태 | 검증 |
| --- | --- | --- | --- |
| Linux GNOME 42 | GJS 레거시 | 동작(별 repo) | 작성자 실기 검증 완료 |
| Linux GNOME 45+ | GJS ESM | 동작(정적/CI 검증) | ESLint + 메타데이터·설치 테스트 + CI (45 실기 없음) |
| macOS 메뉴바 | Swift 또는 rumps (미정) | 예정 | CI 빌드만 (Mac 실기 없음) |
| Windows 트레이 | C#/.NET 또는 pystray (미정) | 예정 | 작성자 Windows 실기 검증 |

> GNOME 42 원본은 작성자 개인 repo(private)에 있고, 이 repo는 배포용으로 GNOME 45+를
> 타깃한다. 42 호환은 별 태그/브랜치로 분리한다 (ESM과 레거시는 한 파일에서 공존 불가).

---

# 로드맵

순서: 공유 코어 → GNOME 45+ → macOS → Windows. 각 프론트엔드는 독립 서브프로젝트로
설계·구현·검증한다.

1. 공유 코어 추출 + OS 경로 추상화 + 테스트 — 완료
2. GNOME 45+ ESM 포팅 — 완료 (정적/CI 검증; shell-version 45–50)
3. macOS 메뉴바 앱
4. Windows 트레이 앱
