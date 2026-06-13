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


class TestPollOnceSafe(unittest.TestCase):
    """in-process GUI worker용 래퍼: 어떤 예외도 state로 변환(절대 raise 안 함)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        d = os.path.join(self._tmp.name, "claude-usage")
        self._p1 = mock.patch.object(core, "STATE_DIR", d)
        self._p2 = mock.patch.object(core, "STATE_PATH", os.path.join(d, "state.json"))
        self._p1.start(); self._p2.start()

    def tearDown(self):
        self._p1.stop(); self._p2.stop(); self._tmp.cleanup()

    def test_passes_through_success(self):
        with mock.patch.object(core, "read_token", return_value="tok"), \
             mock.patch.object(core, "fetch_headers", return_value=(H, 200)):
            state = core.poll_once_safe(NOW, None)
        self.assertTrue(state["ok"])
        self.assertEqual(state["five_h"]["utilization"], 47)

    def test_write_state_oserror_becomes_error_state_not_raise(self):
        # poll_once는 write_state OSError를 전파한다; poll_once_safe는 그것을 삼켜
        # prev 값을 보존한 error_state로 변환해야 한다 (worker가 죽지 않음).
        prev = core.parse_state(H, NOW)
        with mock.patch.object(core, "read_token", return_value="tok"), \
             mock.patch.object(core, "fetch_headers", return_value=(H, 200)), \
             mock.patch.object(core, "write_state", side_effect=OSError("disk full")):
            state = core.poll_once_safe(NOW + 60, prev)
        self.assertFalse(state["ok"])
        self.assertEqual(state["error"]["type"], "internal")
        self.assertEqual(state["five_h"]["utilization"], 47)  # prev 값 보존


if __name__ == "__main__":
    unittest.main()
