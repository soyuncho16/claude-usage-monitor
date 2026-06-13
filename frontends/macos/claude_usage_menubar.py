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
        # poll_once_safe는 어떤 예외도 state로 변환하므로 worker가 조용히 죽지 않는다.
        state = core.poll_once_safe(int(time.time()), self._state)
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
