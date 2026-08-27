# Architecture

단일 원칙: **공유 코어 하나 + 얇은 프론트엔드.** 둘은 `state.json` 파일 하나로만 통신한다.

```text
core/claude_usage_core.py   ← 데이터: 인증·API·헤더파싱·상태쓰기 (Python 표준 라이브러리)
        │  writes
        ▼
  ~/.cache/claude-usage/state.json   ← 유일한 인터페이스
        ▲  reads + spawns core
        │
frontends/gnome/            ← 표시: GNOME Shell 45+ 패널 인디케이터 (GJS ESM)
```

프론트엔드는 코어 스크립트를 spawn하고 state.json을 읽기만 한다. 인증·HTTP는 프론트엔드가
모른다.

---

# 공유 코어

`python3 core/claude_usage_core.py` 1회 실행 → `~/.claude/.credentials.json`의 OAuth
토큰으로 `POST /v1/messages`(max_tokens 1) 호출 → 응답 헤더
`anthropic-ratelimit-unified-*` 파싱 → state.json 원자적 쓰기.

폴링은 한도를 소비하지 않는다 — 사용량은 응답 헤더에 실려오고, 2회 연속 호출에서
utilization이 변하지 않음을 실측 확인했다.

캐시 경로는 XDG 관례를 따른다(`_cache_dir`): `$XDG_CACHE_HOME` 없으면 `~/.cache`.

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

> GNOME 42 원본은 작성자 개인 repo(private)에 있고, 이 repo는 배포용으로 GNOME 45+를
> 타깃한다. 42 호환은 별 태그/브랜치로 분리한다 (ESM과 레거시는 한 파일에서 공존 불가).
