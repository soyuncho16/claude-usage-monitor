# GNOME 45+ ESM Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the verified GNOME 42 panel indicator to the GNOME Shell 45+ ESM extension API, living in `frontends/gnome/` of the distribution repo.

**Architecture:** The frontend spawns the shared Python core (`python3 <ext>/claude_usage_core.py`) on a timer and reads `<cache>/claude-usage/state.json` — identical two-file contract to GNOME 42. Only the display layer changes: legacy `imports.gi` becomes ESM `import`, and the `Extension`/`init()` shape becomes `export default class extends Extension`.

**Tech Stack:** GJS (ESM), GNOME Shell 45–48, Python 3 core (unchanged), ESLint flat config for the offline syntax gate, GitHub Actions CI.

---

# Verification reality

The author runs GNOME 42 and **cannot run a GNOME 45+ shell**. So the automated gates here are:

- `metadata.json` validates as JSON and carries the required keys.
- `extension.js` passes ESLint (catches syntax errors, undefined names, ESM mistakes offline).
- The shared core's 20 tests still pass (the port does not touch `core/`).

The runtime behavior (panel rendering, polling, dropdown) is verified by **static review** plus a **GNOME 45+ tester** (eventually the extensions.gnome.org review). The plan never claims runtime verification the author cannot perform.

---

# File structure

```text
frontends/gnome/
  metadata.json      ← uuid, name, shell-version 45-48
  extension.js       ← ESM port (the deliverable)
  stylesheet.css     ← dot colors + label margin (copied verbatim from GNOME 42)
  install.sh         ← assembles the install dir: frontend files + core .py
  eslint.config.js   ← offline syntax gate
  package.json       ← devDependency: eslint, lint script
  README.md          ← install/uninstall, verification note (already exists, gets rewritten)
.github/workflows/ci.yml  ← core tests + metadata validate + eslint (created here, extended by later plans)
```

The Python core is **not** committed into `frontends/gnome/` — it lives in `core/`. `install.sh` copies `core/claude_usage_core.py` into the install directory at install time, and `gnome-extensions pack` does the same for distribution.

---

# Task 1: Scaffold metadata.json

**Files:**

- Create: `frontends/gnome/metadata.json`
- Create: `tests/test_gnome_metadata.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_gnome_metadata.py
import json
import os
import unittest

META = os.path.join(os.path.dirname(__file__), "..", "frontends", "gnome", "metadata.json")


class TestGnomeMetadata(unittest.TestCase):
    def test_valid_json_and_required_keys(self):
        with open(META) as f:
            m = json.load(f)
        for key in ("uuid", "name", "description", "shell-version", "url"):
            self.assertIn(key, m)

    def test_uuid_is_distribution_not_personal(self):
        with open(META) as f:
            m = json.load(f)
        self.assertEqual(m["uuid"], "claude-usage-monitor@soyuncho16.github.io")
        self.assertNotIn("whth", m["uuid"])  # 개인 repo의 whth.local 잔재 금지

    def test_targets_45_through_48(self):
        with open(META) as f:
            m = json.load(f)
        self.assertEqual(m["shell-version"], ["45", "46", "47", "48"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_gnome_metadata.py -v`
Expected: FAIL — `FileNotFoundError` (metadata.json does not exist yet).

- [ ] **Step 3: Write metadata.json**

```json
{
  "uuid": "claude-usage-monitor@soyuncho16.github.io",
  "name": "Claude Usage Monitor",
  "description": "Shows your Claude subscription 5-hour usage window (utilization % and time until reset) in the top panel.",
  "shell-version": ["45", "46", "47", "48"],
  "url": "https://github.com/soyuncho16/claude-usage-monitor",
  "version": 1
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_gnome_metadata.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add frontends/gnome/metadata.json tests/test_gnome_metadata.py
git commit -m "feat(gnome): add GNOME 45+ extension metadata with distribution uuid"
```

---

# Task 2: Copy the stylesheet verbatim

**Files:**

- Create: `frontends/gnome/stylesheet.css`

The GNOME 42 stylesheet is API-stable across 45+ (St theming is unchanged). Copy it exactly — the dot color thresholds match `_dotClass` in `extension.js`.

- [ ] **Step 1: Write stylesheet.css**

```css
.cu-dot { font-size: 9pt; }
.cu-green { color: #57e389; }
.cu-yellow { color: #f8e45c; }
.cu-red { color: #ff6b6b; }
.cu-gray { color: #9a9996; }
.cu-label { margin-left: 4px; }
```

- [ ] **Step 2: Commit**

```bash
git add frontends/gnome/stylesheet.css
git commit -m "feat(gnome): add panel stylesheet (dot colors + label margin)"
```

---

# Task 3: Port extension.js to the ESM API

**Files:**

- Create: `frontends/gnome/extension.js`

This is the core deliverable. The class body (`_init`, `_set`, `_loadState`, `_fmtRemaining`, `_dotClass`, `_render`, `_nextInterval`, `_schedule`, `_pollNow`, `_startTick`, `_cancelTimer`, `_shutdown`) is **logically identical** to the verified GNOME 42 version. Only three things change for ESM:

- `const {GObject, ...} = imports.gi;` becomes per-namespace `import X from 'gi://X'`.
- `imports.ui.*` becomes `import * as X from 'resource:///org/gnome/shell/ui/X.js'`.
- `function init() { return new Extension() }` with `enable`/`disable` becomes `export default class ClaudeUsageExtension extends Extension`. `Me.path` becomes `this.path` (passed into the Indicator constructor so the spawn knows where the core script lives).

- [ ] **Step 1: Write extension.js**

```javascript
import GObject from 'gi://GObject';
import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import St from 'gi://St';
import Clutter from 'gi://Clutter';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const STATE_PATH = GLib.build_filenamev(
    [GLib.get_user_cache_dir(), 'claude-usage', 'state.json']);
const NORMAL_S = 600;        // 평소 폴링 간격
const FAST_S = 60;           // 리셋 임박 폴링 간격
const FAST_WINDOW_S = 1800;  // 리셋 30분 전부터 가속
const TICK_S = 30;           // 카운트다운 라벨 재계산 주기
const SPAWN_TIMEOUT_S = 8;   // poller 강제 종료 한도

const Indicator = GObject.registerClass(
class Indicator extends PanelMenu.Button {
    _init(pollerPath) {
        super._init(0.0, 'Claude Usage');
        this._poller = pollerPath;  // ESM: Me.path 대신 Extension 인스턴스의 this.path를 받는다
        this._state = null;

        const box = new St.BoxLayout();
        this._dot = new St.Label({
            text: '●',
            y_align: Clutter.ActorAlign.CENTER,
            style_class: 'cu-dot cu-gray',
        });
        this._label = new St.Label({
            text: '…',
            y_align: Clutter.ActorAlign.CENTER,
            style_class: 'cu-label',
        });
        box.add_child(this._dot);
        box.add_child(this._label);
        this.add_child(box);

        this._row5h = new PopupMenu.PopupMenuItem('5시간 창  —', { reactive: false });
        this._row7d = new PopupMenu.PopupMenuItem('7일 창  —', { reactive: false });
        this._rowMeta = new PopupMenu.PopupMenuItem('갱신 전', { reactive: false });
        this._rowRefresh = new PopupMenu.PopupMenuItem('지금 갱신');
        this._rowRefresh.connect('activate', () => this._pollNow());
        this.menu.addMenuItem(this._row5h);
        this.menu.addMenuItem(this._row7d);
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        this.menu.addMenuItem(this._rowMeta);
        this.menu.addMenuItem(this._rowRefresh);
    }

    _set(dotClass, text) {
        this._dot.style_class = `cu-dot ${dotClass}`;
        this._label.text = text;
    }

    _loadState() {
        try {
            const [ok, bytes] = GLib.file_get_contents(STATE_PATH);
            this._state = ok ? JSON.parse(new TextDecoder().decode(bytes)) : null;
        } catch (e) {
            this._state = null; // 파일 없음/깨짐 → 첫 실행 표시
        }
    }

    _fmtRemaining(resetsAt) {
        const s = Math.max(0, resetsAt - Math.floor(Date.now() / 1000));
        const h = Math.floor(s / 3600);
        const m = Math.floor((s % 3600) / 60);
        return h > 0 ? `${h}h${String(m).padStart(2, '0')}m` : `${m}m`;
    }

    _dotClass(pct) {
        if (pct >= 85) return 'cu-red';
        if (pct >= 60) return 'cu-yellow';
        return 'cu-green';
    }

    _render() {
        const s = this._state;
        if (!s) {
            this._set('cu-gray', '…');
            this._rowMeta.label.text = '아직 데이터 없음';
            return;
        }
        const err = s.error ? s.error.type : null;
        const f = s.five_h;

        if (err === 'no_creds' || err === 'auth_expired') {
            this._set('cu-gray', '로그인 필요');
        } else if (!f || f.utilization === null || f.utilization === undefined) {
            this._set('cu-gray', '…');
        } else {
            const remain = f.resets_at ? ` · ${this._fmtRemaining(f.resets_at)}` : '';
            let cls;
            if (err === 'rate_limited') cls = 'cu-red';
            else if (s.ok === false) cls = 'cu-gray'; // 오래된 값 + 오류
            else cls = this._dotClass(f.utilization);
            this._set(cls, `${f.utilization}%${remain}`);
        }

        this._row5h.label.text = (f && f.utilization !== null && f.utilization !== undefined)
            ? `5시간 창  ${f.utilization}% 사용` +
              (f.resets_at ? ` · ${this._fmtRemaining(f.resets_at)} 후 리셋` : '')
            : '5시간 창  —';
        const d = s.seven_d;
        this._row7d.label.text = (d && d.utilization !== null && d.utilization !== undefined)
            ? `7일 창  ${d.utilization}% 사용`
            : '7일 창  —';

        const age = Math.max(0, Math.floor(Date.now() / 1000) - (s.fetched_at || 0));
        const ageTxt = age < 60 ? '방금' : `${Math.floor(age / 60)}분 전`;
        this._rowMeta.label.text = err
            ? `오류: ${err} · ${ageTxt} 갱신`
            : `상태: ${s.status || 'OK'} · ${ageTxt} 갱신`;
    }

    _nextInterval() {
        const s = this._state;
        if (s && s.five_h && s.five_h.resets_at) {
            const remain = s.five_h.resets_at - Math.floor(Date.now() / 1000);
            if (remain > 0 && remain <= FAST_WINDOW_S)
                return FAST_S; // 리셋 30분 전 → 1분 간격
        }
        return NORMAL_S;
    }

    _schedule() {
        this._cancelTimer();
        this._pollId = GLib.timeout_add_seconds(
            GLib.PRIORITY_DEFAULT, this._nextInterval(), () => {
                this._pollId = 0;
                this._pollNow();
                return GLib.SOURCE_REMOVE; // 매번 재등록 → 간격 전환 자연 반영
            });
    }

    _pollNow() {
        if (this._proc) return; // 중복 spawn 방지
        let proc;
        try {
            proc = Gio.Subprocess.new(
                ['python3', this._poller], Gio.SubprocessFlags.NONE);
        } catch (e) {
            this._loadState();
            this._render();
            this._schedule();
            return;
        }
        this._proc = proc;
        this._guardId = GLib.timeout_add_seconds(
            GLib.PRIORITY_DEFAULT, SPAWN_TIMEOUT_S, () => {
                this._guardId = 0;
                if (this._proc) this._proc.force_exit();
                return GLib.SOURCE_REMOVE;
            });
        proc.wait_async(null, () => {
            if (this._destroyed) return; // destroy 후 콜백 방어
            if (this._guardId) {
                GLib.source_remove(this._guardId);
                this._guardId = 0;
            }
            this._proc = null;
            this._loadState();
            this._render();
            this._schedule();
        });
    }

    _startTick() {
        this._tickId = GLib.timeout_add_seconds(
            GLib.PRIORITY_DEFAULT, TICK_S, () => {
                this._render(); // 카운트다운만 재계산 (폴링 아님)
                return GLib.SOURCE_CONTINUE;
            });
    }

    _cancelTimer() {
        if (this._pollId) {
            GLib.source_remove(this._pollId);
            this._pollId = 0;
        }
    }

    _shutdown() {
        this._destroyed = true;
        this._cancelTimer();
        if (this._tickId) {
            GLib.source_remove(this._tickId);
            this._tickId = 0;
        }
        if (this._guardId) {
            GLib.source_remove(this._guardId);
            this._guardId = 0;
        }
        if (this._proc) {
            this._proc.force_exit();
            this._proc = null;
        }
    }
});

export default class ClaudeUsageExtension extends Extension {
    enable() {
        const pollerPath = GLib.build_filenamev([this.path, 'claude_usage_core.py']);
        this._indicator = new Indicator(pollerPath);
        Main.panel.addToStatusArea('claude-usage', this._indicator);
        this._indicator._loadState();
        this._indicator._render();
        this._indicator._startTick();
        this._indicator._pollNow(); // enable 즉시 1회 폴링
    }

    disable() {
        this._indicator._shutdown();
        this._indicator.destroy();
        this._indicator = null;
    }
}
```

- [ ] **Step 2: Manual ESM checklist (no shell available)**

Confirm each ESM-specific point by reading the file:

- No `imports.gi` / `imports.ui` / `imports.misc.extensionUtils` anywhere.
- Every namespace used (`GObject`, `GLib`, `Gio`, `St`, `Clutter`, `Main`, `PanelMenu`, `PopupMenu`, `Extension`) has a matching `import`.
- `export default class ... extends Extension` exists; there is no `function init()`.
- The spawn path comes from `this.path` (via the constructor arg), not a removed `Me`.
- `TextDecoder` is used unprefixed (it is a GJS global in 45+).

ESLint in Task 4 enforces most of this automatically; this checklist is the human read.

- [ ] **Step 3: Commit**

```bash
git add frontends/gnome/extension.js
git commit -m "feat(gnome): port panel indicator to GNOME 45+ ESM extension API"
```

---

# Task 4: ESLint syntax gate

**Files:**

- Create: `frontends/gnome/package.json`
- Create: `frontends/gnome/eslint.config.js`

ESLint is the only offline gate that catches JS syntax errors, missing imports, and undefined names for code the author cannot run. GJS provides shell globals (`globalThis`, `TextDecoder`, `console`, `log`, `print`) — declare them so `no-undef` does not false-positive.

- [ ] **Step 1: Write package.json**

```json
{
  "name": "claude-usage-monitor-gnome",
  "version": "1.0.0",
  "private": true,
  "description": "GNOME 45+ frontend lint tooling",
  "scripts": {
    "lint": "eslint extension.js"
  },
  "devDependencies": {
    "eslint": "^9.0.0"
  }
}
```

- [ ] **Step 2: Write eslint.config.js (flat config)**

```javascript
export default [
    {
        files: ['extension.js'],
        languageOptions: {
            ecmaVersion: 'latest',
            sourceType: 'module',
            globals: {
                globalThis: 'readonly',
                TextDecoder: 'readonly',
                TextEncoder: 'readonly',
                console: 'readonly',
                log: 'readonly',
                logError: 'readonly',
                print: 'readonly',
            },
        },
        rules: {
            'no-undef': 'error',
            'no-unused-vars': 'warn',
        },
    },
];
```

- [ ] **Step 3: Run the lint gate**

Run: `cd frontends/gnome && npm install && npm run lint`
Expected: PASS with no errors. If ESLint reports `no-undef` for a `gi://` import name, the import is missing — fix `extension.js`.

> If a CI-only node toolchain is undesirable, this task can be dropped and the gate becomes static review alone. Keeping it is recommended precisely because the author cannot run the shell.

- [ ] **Step 4: Commit**

```bash
git add frontends/gnome/package.json frontends/gnome/eslint.config.js
git commit -m "build(gnome): add eslint flat config as offline syntax gate"
```

---

# Task 5: Install script + README

**Files:**

- Create: `frontends/gnome/install.sh`
- Modify: `frontends/gnome/README.md`

The install dir must contain the frontend files **and** the Python core. Because the two come from different repo directories, `install.sh` assembles the target by copying (not whole-dir symlinking like GNOME 42). Re-run after edits during development.

- [ ] **Step 1: Write install.sh**

```bash
#!/usr/bin/env bash
set -euo pipefail

UUID="claude-usage-monitor@soyuncho16.github.io"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
DST="$HOME/.local/share/gnome-shell/extensions/$UUID"

mkdir -p "$DST"
cp "$HERE/extension.js" "$HERE/metadata.json" "$HERE/stylesheet.css" "$DST/"
cp "$REPO/core/claude_usage_core.py" "$DST/claude_usage_core.py"

echo "installed: $DST"
echo
echo "순서가 중요하다 — 셸이 확장을 인식한 뒤에 enable한다:"
echo "  1) 셸 재시작(X11): Alt+F2 → r → Enter   (Wayland이면 로그아웃/로그인)"
echo "  2) 활성화: gnome-extensions enable $UUID"
echo
echo "확장 파일을 수정하면 install.sh를 다시 실행한 뒤 셸을 재시작한다."
```

- [ ] **Step 2: Make it executable**

Run: `chmod +x frontends/gnome/install.sh`

- [ ] **Step 3: Rewrite frontends/gnome/README.md**

````markdown
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
````

- [ ] **Step 4: Commit**

```bash
git add frontends/gnome/install.sh frontends/gnome/README.md
git commit -m "feat(gnome): add install script and rewrite README"
```

---

# Task 6: GitHub Actions CI

**Files:**

- Create: `.github/workflows/ci.yml`

This workflow is created here and **extended by the macOS and Windows plans** (each adds a job). For now it runs the Python core tests, validates the GNOME metadata, and lints `extension.js`.

- [ ] **Step 1: Write ci.yml**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  core:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.x"
      - name: Run core + frontend metadata tests
        run: python3 -m pytest tests/ -v

  gnome-lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - name: Lint GNOME extension.js
        working-directory: frontends/gnome
        run: |
          npm install
          npm run lint
```

- [ ] **Step 2: Verify the test job locally**

Run: `python3 -m pytest tests/ -v`
Expected: PASS — all core tests plus `test_gnome_metadata.py` (23 total: 20 core + 3 metadata).

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: run core tests, GNOME metadata tests, and extension lint"
```

---

# Final review

After all tasks, dispatch a final reviewer over the whole `frontends/gnome/` diff. Then verify:

- `python3 -m pytest tests/ -v` — all pass.
- `cd frontends/gnome && npm run lint` — clean.
- The ESM checklist from Task 3 Step 2 holds.

Then hand off via superpowers:finishing-a-development-branch. Update `ARCHITECTURE.md` (GNOME 45+ row → 상태 "동작(정적/CI 검증)") and the project memory in the same pass.
