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
