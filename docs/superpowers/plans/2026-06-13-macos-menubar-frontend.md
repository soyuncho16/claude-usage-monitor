# macOS Menu Bar Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A macOS menu bar app (rumps) that shows the Claude 5-hour usage window as `🟢 47% · 3h12m` and a dropdown with 5h/7d/status/refresh, polling the shared core in-process.

**Architecture:** Single process. The rumps app **imports** `claude_usage_core` and calls `poll_once(now)` on a background thread (so the 7-second network call never freezes the menu bar); results are picked up and rendered on the main thread by a short repeating timer. All display formatting and the polling cadence live in a **rumps-free pure module** (`usage_display.py`) so they are unit-tested on Linux/CI without a Mac.

**Tech Stack:** Python 3, rumps (PyObjC-based menu bar framework), py2app for packaging, the existing shared core.

---

# Verification reality

The author **has no Mac**. So:

- All formatting and cadence logic lives in `usage_display.py` (no PyObjC import) and is **fully unit-tested on Linux** — this is real, runnable coverage.
- The new core function `poll_once()` is unit-tested on Linux.
- The rumps GUI shell (`claude_usage_menubar.py`) imports PyObjC and **cannot run on Linux**; it is verified by static review plus a **CI macOS build** (`py2app` on a `macos-latest` runner proves it builds and bundles). Actual menu bar behavior ships **unverified** — the README and release notes must say so.

The thin GUI shell is deliberately kept logic-free so the unverifiable surface is as small as possible.

---

# File structure

```text
core/claude_usage_core.py        ← MODIFY: extract poll_once(); main() delegates to it
frontends/macos/
  usage_display.py               ← pure formatting + cadence (no rumps) — testable
  claude_usage_menubar.py        ← rumps GUI shell (thin; imports core + usage_display)
  setup.py                       ← py2app bundle build
  requirements.txt               ← rumps, py2app
  README.md                      ← build/run/autostart + verification note (rewrite)
tests/
  test_poll_once.py              ← core poll_once() coverage
  test_macos_display.py          ← usage_display coverage (the bulk of real verification)
.github/workflows/ci.yml         ← MODIFY: add macos-build job
```

---

# Task 1: Extract poll_once() in the shared core

The macOS app needs the full read-token to write-state orchestration as a callable that returns the state and never raises. Today that orchestration is inline in `main()`. Extract it; have `main()` delegate. No existing test calls `main()` or `poll_once()`, so the 20 current tests stay green.

**Files:**

- Modify: `core/claude_usage_core.py` (replace the body of `main`, add `poll_once`)
- Create: `tests/test_poll_once.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_poll_once.py
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
import claude_usage_core as core

NOW = 1_749_700_000
H = {
    "anthropic-ratelimit-unified-5h-utilization": "0.47",
    "anthropic-ratelimit-unified-5h-reset": "1749730000",
    "anthropic-ratelimit-unified-status": "allowed",
}


class TestPollOnce(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        d = os.path.join(self._tmp.name, "claude-usage")
        self._p1 = mock.patch.object(core, "STATE_DIR", d)
        self._p2 = mock.patch.object(core, "STATE_PATH", os.path.join(d, "state.json"))
        self._p1.start(); self._p2.start()

    def tearDown(self):
        self._p1.stop(); self._p2.stop(); self._tmp.cleanup()

    def test_success_returns_and_writes_state(self):
        with mock.patch.object(core, "read_token", return_value="tok"), \
             mock.patch.object(core, "fetch_headers", return_value=(H, 200)):
            state = core.poll_once(NOW)
        self.assertTrue(state["ok"])
        self.assertEqual(state["five_h"]["utilization"], 47)
        self.assertEqual(core.load_prev(), state)  # write_state까지 수행됨

    def test_429_injects_rate_limited_but_stays_ok(self):
        with mock.patch.object(core, "read_token", return_value="tok"), \
             mock.patch.object(core, "fetch_headers", return_value=(H, 429)):
            state = core.poll_once(NOW)
        self.assertTrue(state["ok"])
        self.assertEqual(state["error"]["type"], "rate_limited")

    def test_poller_error_returns_error_state_not_raise(self):
        core.write_state(core.parse_state(H, NOW))  # 직전 성공 값
        with mock.patch.object(core, "read_token",
                               side_effect=core.PollerError("network", "boom")):
            state = core.poll_once(NOW + 60)
        self.assertFalse(state["ok"])
        self.assertEqual(state["error"]["type"], "network")
        self.assertEqual(state["five_h"]["utilization"], 47)  # 직전 값 보존


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_poll_once.py -v`
Expected: FAIL — `AttributeError: module 'claude_usage_core' has no attribute 'poll_once'`.

- [ ] **Step 3: Add poll_once and make main delegate**

Replace the entire `main` function at the bottom of `core/claude_usage_core.py` with:

```python
def poll_once(now, dump_headers=False):
    """1회 폴링 후 항상 state dict를 반환한다(예외를 던지지 않음).

    성공: 헤더 파싱 후 write_state. 429면 error에 rate_limited 주입(ok는 True 유지).
    실패: error_state를 직전 값 위에 써서 반환(ok False).

    frontends/macos는 이 함수를 import해 백그라운드 스레드에서 호출하고,
    CLI(main)와 spawn 기반 프론트엔드(GNOME/Windows)는 main을 통해 호출한다.
    """
    try:
        token = read_token(now)
        headers, status = fetch_headers(token)
        if dump_headers:
            print(f"# HTTP {status}", file=sys.stderr)
            for k in sorted(headers):
                print(f"{k}: {headers[k]}", file=sys.stderr)
        state = parse_state(headers, now)
        if status == 429:
            state["error"] = {"type": "rate_limited", "message": "HTTP 429"}
        write_state(state)
        return state
    except PollerError as e:
        state = error_state(e, load_prev(), now)
        write_state(state)
        return state


def main(argv):
    # write_state의 OSError는 의도적으로 전파한다 — 캐시 쓰기 실패는 시스템 이상이며
    # traceback 그대로가 진단에 유리. 이전 state.json은 보존되어 데이터 손실도 없다.
    now = int(time.time())
    state = poll_once(now, dump_headers=("--dump-headers" in argv))
    if not state.get("ok"):
        err = state.get("error") or {}
        print(f"error[{err.get('type')}]: {err.get('message')}", file=sys.stderr)
        return 1
    return 0  # 429(rate_limited)는 ok=True라 0을 반환 — 기존 동작 보존
```

> Note: `poll_once` lets a `write_state` `OSError` propagate exactly as the old `main` did. The 429-returns-0 behavior is preserved because `parse_state` keeps `ok: True` and only injects the `error` field.

- [ ] **Step 4: Run the new test and the full suite**

Run: `python3 -m pytest tests/test_poll_once.py tests/test_core.py -v`
Expected: PASS — 3 new + 20 existing = 23.

- [ ] **Step 5: Commit**

```bash
git add core/claude_usage_core.py tests/test_poll_once.py
git commit -m "refactor(core): extract poll_once() for in-process frontends; main delegates"
```

---

# Task 2: Pure display + cadence module

All formatting and the polling cadence, mirroring `extension.js` exactly. No rumps import — so it runs and is tested anywhere. Color is expressed as a status emoji (the macOS menu bar text cannot carry inline color cheaply).

**Files:**

- Create: `frontends/macos/usage_display.py`
- Create: `tests/test_macos_display.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_macos_display.py
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "frontends", "macos"))
import usage_display as d

NOW = 1_749_700_000


def st(**kw):
    base = {"ok": True, "fetched_at": NOW, "five_h": None, "seven_d": None,
            "status": "allowed", "error": None}
    base.update(kw)
    return base


class TestFmtRemaining(unittest.TestCase):
    def test_hours_and_minutes(self):
        self.assertEqual(d.fmt_remaining(NOW + 3 * 3600 + 12 * 60, NOW), "3h12m")

    def test_minutes_only(self):
        self.assertEqual(d.fmt_remaining(NOW + 12 * 60, NOW), "12m")

    def test_zero_padding(self):
        self.assertEqual(d.fmt_remaining(NOW + 3 * 3600 + 5 * 60, NOW), "3h05m")

    def test_past_clamps_to_zero(self):
        self.assertEqual(d.fmt_remaining(NOW - 100, NOW), "0m")


class TestDotEmoji(unittest.TestCase):
    def test_thresholds(self):
        self.assertEqual(d.dot_emoji(0), d.GREEN)
        self.assertEqual(d.dot_emoji(59), d.GREEN)
        self.assertEqual(d.dot_emoji(60), d.YELLOW)
        self.assertEqual(d.dot_emoji(84), d.YELLOW)
        self.assertEqual(d.dot_emoji(85), d.RED)
        self.assertEqual(d.dot_emoji(100), d.RED)


class TestTitle(unittest.TestCase):
    def test_none_state(self):
        self.assertEqual(d.title_text(None, NOW), f"{d.GRAY} …")

    def test_login_needed(self):
        s = st(ok=False, error={"type": "no_creds", "message": "x"})
        self.assertEqual(d.title_text(s, NOW), f"{d.GRAY} 로그인 필요")

    def test_normal(self):
        s = st(five_h={"utilization": 47, "resets_at": NOW + 3 * 3600 + 12 * 60})
        self.assertEqual(d.title_text(s, NOW), f"{d.GREEN} 47% · 3h12m")

    def test_no_reset_omits_countdown(self):
        s = st(five_h={"utilization": 47, "resets_at": None})
        self.assertEqual(d.title_text(s, NOW), f"{d.GREEN} 47%")

    def test_rate_limited_is_red(self):
        s = st(five_h={"utilization": 30, "resets_at": None},
               error={"type": "rate_limited", "message": "x"})
        self.assertEqual(d.title_text(s, NOW), f"{d.RED} 30%")

    def test_stale_with_error_is_gray(self):
        s = st(ok=False, five_h={"utilization": 30, "resets_at": None},
               error={"type": "network", "message": "x"})
        self.assertEqual(d.title_text(s, NOW), f"{d.GRAY} 30%")


class TestMenuRows(unittest.TestCase):
    def test_5h(self):
        s = st(five_h={"utilization": 47, "resets_at": NOW + 3 * 3600 + 12 * 60})
        self.assertEqual(d.menu_5h(s, NOW), "5시간 창  47% 사용 · 3h12m 후 리셋")

    def test_7d_present(self):
        s = st(seven_d={"utilization": 12, "resets_at": None})
        self.assertEqual(d.menu_7d(s), "7일 창  12% 사용")

    def test_7d_absent(self):
        self.assertEqual(d.menu_7d(st()), "7일 창  —")

    def test_meta_fresh(self):
        self.assertEqual(d.menu_meta(st(fetched_at=NOW), NOW), "상태: allowed · 방금 갱신")

    def test_meta_error(self):
        s = st(error={"type": "network", "message": "x"}, fetched_at=NOW - 120)
        self.assertEqual(d.menu_meta(s, NOW), "오류: network · 2분 전 갱신")


class TestNextInterval(unittest.TestCase):
    def test_normal_far_from_reset(self):
        s = st(five_h={"utilization": 10, "resets_at": NOW + 4 * 3600})
        self.assertEqual(d.next_interval(s, NOW), d.NORMAL_S)

    def test_fast_within_window(self):
        s = st(five_h={"utilization": 90, "resets_at": NOW + 600})
        self.assertEqual(d.next_interval(s, NOW), d.FAST_S)

    def test_no_state_is_normal(self):
        self.assertEqual(d.next_interval(None, NOW), d.NORMAL_S)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_macos_display.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'usage_display'`.

- [ ] **Step 3: Write usage_display.py**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_macos_display.py -v`
Expected: PASS (all cases).

- [ ] **Step 5: Commit**

```bash
git add frontends/macos/usage_display.py tests/test_macos_display.py
git commit -m "feat(macos): pure display + cadence module with full unit tests"
```

---

# Task 3: rumps menu bar shell

A thin GUI shell. It owns no formatting logic — it calls `usage_display` for every string and `core.poll_once` for data. The network call runs on a daemon thread; a 5-second main-thread timer picks up results, schedules the next poll by `next_interval`, and re-renders the countdown.

> This file imports PyObjC via rumps and **cannot be imported on Linux** — keep it out of the test suite. It is verified by static review and the CI macOS build only.

**Files:**

- Create: `frontends/macos/claude_usage_menubar.py`

- [ ] **Step 1: Write claude_usage_menubar.py**

```python
#!/usr/bin/env python3
"""Claude Usage Monitor — macOS 메뉴바 앱 (rumps).

단일 프로세스. 공유 코어를 import해 백그라운드 스레드에서 poll_once를 호출하고,
메인스레드 타이머가 결과 수거 + 폴링 스케줄 + 카운트다운 재계산을 담당한다.
"""
import os
import sys
import threading
import time

# 공유 코어와 표시 모듈을 import 경로에 올린다 (dev 실행용; py2app 번들은 setup.py가 포함).
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "core"))
sys.path.insert(0, _HERE)

import rumps
import claude_usage_core as core
import usage_display as disp

TICK_S = 5  # 메인스레드 틱: 결과 수거 + 폴링 스케줄 + 카운트다운 재계산


class ClaudeUsageApp(rumps.App):
    def __init__(self):
        super().__init__("Claude Usage", title=f"{disp.GRAY} …", quit_button="종료")
        self.row_5h = rumps.MenuItem("5시간 창  —")
        self.row_7d = rumps.MenuItem("7일 창  —")
        self.row_meta = rumps.MenuItem("갱신 전")
        self.menu = [
            self.row_5h,
            self.row_7d,
            None,  # 구분선
            self.row_meta,
            rumps.MenuItem("지금 갱신", callback=self.on_refresh),
        ]
        self._state = core.load_prev()
        self._pending = None
        self._lock = threading.Lock()
        self._worker = None
        self._next_poll_at = 0  # 시작 즉시 1회 폴링
        self._render()
        self._timer = rumps.Timer(self._on_tick, TICK_S)
        self._timer.start()

    def _on_tick(self, _timer):
        now = int(time.time())
        with self._lock:
            if self._pending is not None:
                self._state = self._pending
                self._pending = None
        if now >= self._next_poll_at and (self._worker is None or not self._worker.is_alive()):
            self._launch_poll(now)
        self._render()

    def _launch_poll(self, now):
        self._next_poll_at = now + disp.next_interval(self._state, now)
        self._worker = threading.Thread(target=self._poll_worker, daemon=True)
        self._worker.start()

    def _poll_worker(self):
        # 네트워크 호출은 여기(백그라운드)에서만 — 메뉴바를 멈추지 않는다.
        state = core.poll_once(int(time.time()))
        with self._lock:
            self._pending = state

    def on_refresh(self, _sender):
        self._next_poll_at = 0  # 다음 틱에서 즉시 폴링

    def _render(self):
        now = int(time.time())
        self.title = disp.title_text(self._state, now)
        self.row_5h.title = disp.menu_5h(self._state, now)
        self.row_7d.title = disp.menu_7d(self._state)
        self.row_meta.title = disp.menu_meta(self._state, now)


def main():
    ClaudeUsageApp().run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Static review checklist**

- No string is built inline — every label comes from `disp.*`.
- The only network call site is `_poll_worker` (background thread); the main thread never blocks on I/O.
- UI mutations (`self.title`, `row.title`) happen only inside `_render`, called from the main-thread timer.
- rumps auto-adds a Quit item; we relabel it via `quit_button="종료"`.

- [ ] **Step 3: Commit**

```bash
git add frontends/macos/claude_usage_menubar.py
git commit -m "feat(macos): rumps menu bar shell (thin; logic delegated to core + usage_display)"
```

---

# Task 4: Packaging + README

**Files:**

- Create: `frontends/macos/requirements.txt`
- Create: `frontends/macos/setup.py`
- Modify: `frontends/macos/README.md`

- [ ] **Step 1: Write requirements.txt**

```text
rumps>=0.4.0
py2app>=0.28
```

- [ ] **Step 2: Write setup.py (py2app)**

```python
"""py2app 번들 빌드 — Mac에서만 실행. 공유 코어와 표시 모듈을 번들에 포함한다.

    cd frontends/macos
    pip install -r requirements.txt
    python setup.py py2app        # dist/Claude Usage Monitor.app
"""
import os
import sys

from setuptools import setup

# 공유 코어를 모듈 탐색 경로에 올려 py2app이 수집하도록 한다.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "core"))

APP = ["claude_usage_menubar.py"]
OPTIONS = {
    "argv_emulation": False,
    "plist": {
        "LSUIElement": True,  # Dock 아이콘 없이 메뉴바 전용
        "CFBundleName": "Claude Usage Monitor",
        "CFBundleIdentifier": "io.github.soyuncho16.claude-usage-monitor",
    },
    "includes": ["claude_usage_core", "usage_display"],
    "packages": ["rumps"],
}

setup(
    app=APP,
    name="Claude Usage Monitor",
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
```

- [ ] **Step 3: Rewrite frontends/macos/README.md**

````markdown
# macOS frontend

macOS 메뉴바 앱. 메뉴바에 `🟢 47% · 3h12m`(상태 이모지 + 5시간 사용률 + 리셋 카운트다운)을
표시하고, 클릭하면 5시간/7일/상태/지금 갱신 드롭다운을 연다. 단일 프로세스로,
공유 코어를 import해 백그라운드 스레드에서 폴링한다(10분 주기, 리셋 30분 전부터 1분).

## 개발 실행

```bash
pip install -r requirements.txt
python claude_usage_menubar.py     # repo 루트에서 실행해도 됨 (core를 자동 import)
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
````

- [ ] **Step 4: Commit**

```bash
git add frontends/macos/requirements.txt frontends/macos/setup.py frontends/macos/README.md
git commit -m "build(macos): py2app packaging, requirements, README with verification note"
```

---

# Task 5: CI macOS build job

**Files:**

- Modify: `.github/workflows/ci.yml` (add `macos-build` job)

The display/core tests already run in the `core` job on ubuntu. This job proves the rumps shell builds and bundles on a real macOS runner — the only Mac-side check available.

- [ ] **Step 1: Add the job**

```yaml
  macos-build:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.x"
      - name: Build the menu bar app bundle
        working-directory: frontends/macos
        run: |
          pip install -r requirements.txt
          python setup.py py2app
      - name: Assert the .app bundle exists
        working-directory: frontends/macos
        run: test -d "dist/Claude Usage Monitor.app"
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci(macos): build and assert the py2app bundle on a macos runner"
```

---

# Final review

After all tasks, dispatch a final reviewer over `core/` + `frontends/macos/`. Verify:

- `python3 -m pytest tests/ -v` — all pass (core 20 + gnome metadata 3 + poll_once 3 + macos display ~20).
- `frontends/macos/claude_usage_menubar.py` contains no formatting logic and no main-thread I/O.

Then hand off via superpowers:finishing-a-development-branch. Update `ARCHITECTURE.md` (macOS row → "동작(빌드/CI), 런타임 미검증") and the project memory.
