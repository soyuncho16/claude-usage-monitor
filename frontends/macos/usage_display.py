"""순수 표시 + 폴링 주기 로직 — rumps GUI에서 분리해 Mac 없이도 테스트한다.

GNOME extension.js의 _render/_fmtRemaining/_dotClass/_nextInterval와 동일 정책.
메뉴바 텍스트에 인라인 색을 넣기 어려워 색을 이모지로 표현한다.
"""

NORMAL_S = 600          # 평소 폴링 간격
FAST_S = 60             # 리셋 임박 폴링 간격
FAST_WINDOW_S = 1800    # 리셋 30분 전부터 가속

GREEN, YELLOW, RED, GRAY = "🟢", "🟡", "🔴", "⚪"


def fmt_remaining(resets_at, now):
    s = max(0, resets_at - now)
    h, m = s // 3600, (s % 3600) // 60
    return f"{h}h{m:02d}m" if h > 0 else f"{m}m"


def dot_emoji(pct):
    if pct >= 85:
        return RED
    if pct >= 60:
        return YELLOW
    return GREEN


def _err(state):
    e = state.get("error")
    return e["type"] if e else None


def _five(state):
    f = state.get("five_h")
    return f if f and f.get("utilization") is not None else None


def title_text(state, now):
    if not state:
        return f"{GRAY} …"
    err = _err(state)
    if err in ("no_creds", "auth_expired"):
        return f"{GRAY} 로그인 필요"
    f = _five(state)
    if not f:
        return f"{GRAY} …"
    remain = f" · {fmt_remaining(f['resets_at'], now)}" if f.get("resets_at") else ""
    if err == "rate_limited":
        emoji = RED
    elif state.get("ok") is False:
        emoji = GRAY  # 오래된 값 + 오류
    else:
        emoji = dot_emoji(f["utilization"])
    return f"{emoji} {f['utilization']}%{remain}"


def menu_5h(state, now):
    f = _five(state) if state else None
    if not f:
        return "5시간 창  —"
    suffix = f" · {fmt_remaining(f['resets_at'], now)} 후 리셋" if f.get("resets_at") else ""
    return f"5시간 창  {f['utilization']}% 사용{suffix}"


def menu_7d(state):
    d = state.get("seven_d") if state else None
    if d and d.get("utilization") is not None:
        return f"7일 창  {d['utilization']}% 사용"
    return "7일 창  —"


def menu_meta(state, now):
    if not state:
        return "아직 데이터 없음"
    age = max(0, now - (state.get("fetched_at") or 0))
    age_txt = "방금" if age < 60 else f"{age // 60}분 전"
    err = _err(state)
    if err:
        return f"오류: {err} · {age_txt} 갱신"
    return f"상태: {state.get('status') or 'OK'} · {age_txt} 갱신"


def next_interval(state, now):
    f = state.get("five_h") if state else None
    if f and f.get("resets_at"):
        remain = f["resets_at"] - now
        if 0 < remain <= FAST_WINDOW_S:
            return FAST_S
    return NORMAL_S
