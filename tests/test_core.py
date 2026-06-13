#!/usr/bin/env python3
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
import claude_usage_core as poller

NOW = 1_749_700_000

# 실측 형식(2026-06-12 검증): utilization은 0.0-1.0 분수, reset은 epoch 정수
H_FRACTION = {
    "anthropic-ratelimit-unified-5h-utilization": "0.47",
    "anthropic-ratelimit-unified-7d-utilization": "0.12",
    "anthropic-ratelimit-unified-status": "allowed",
    "anthropic-ratelimit-unified-5h-reset": "2026-06-12T12:00:00Z",
}
H_PERCENT = {
    "anthropic-ratelimit-unified-5h-utilization": "47",
    "anthropic-ratelimit-unified-5h-reset": "1749730000",
}
H_SECONDS_RESET = {
    "anthropic-ratelimit-unified-5h-utilization": "0.05",
    "anthropic-ratelimit-unified-5h-reset": "1800",
}

# 실측 헤더 전체 세트 (2026-06-12 실측 12개)
H_REAL = {
    "anthropic-ratelimit-unified-5h-reset": "1781276400",
    "anthropic-ratelimit-unified-5h-status": "allowed",
    "anthropic-ratelimit-unified-5h-utilization": "0.08",
    "anthropic-ratelimit-unified-7d-reset": "1781341200",
    "anthropic-ratelimit-unified-7d-status": "allowed",
    "anthropic-ratelimit-unified-7d-utilization": "0.57",
    "anthropic-ratelimit-unified-fallback-percentage": "0.5",
    "anthropic-ratelimit-unified-overage-disabled-reason": "org_level_disabled",
    "anthropic-ratelimit-unified-overage-status": "rejected",
    "anthropic-ratelimit-unified-representative-claim": "five_hour",
    "anthropic-ratelimit-unified-reset": "1781276400",
    "anthropic-ratelimit-unified-status": "allowed",
}


class TestParseState(unittest.TestCase):
    def test_fraction_utilization_and_iso_reset(self):
        s = poller.parse_state(H_FRACTION, NOW)
        self.assertTrue(s["ok"])
        self.assertEqual(s["five_h"]["utilization"], 47)
        self.assertEqual(s["seven_d"]["utilization"], 12)
        self.assertEqual(s["status"], "allowed")
        self.assertEqual(s["five_h"]["resets_at"], 1781265600)  # 2026-06-12T12:00:00Z

    def test_percent_utilization_and_epoch_reset(self):
        s = poller.parse_state(H_PERCENT, NOW)
        self.assertEqual(s["five_h"]["utilization"], 47)
        self.assertEqual(s["five_h"]["resets_at"], 1749730000)

    def test_seconds_remaining_reset(self):
        s = poller.parse_state(H_SECONDS_RESET, NOW)
        self.assertEqual(s["five_h"]["resets_at"], NOW + 1800)

    def test_missing_5h_utilization_raises_parse_error(self):
        with self.assertRaises(poller.PollerError) as cm:
            poller.parse_state({"anthropic-ratelimit-unified-status": "allowed"}, NOW)
        self.assertEqual(cm.exception.etype, "parse")

    def test_7d_absent_is_none_not_error(self):
        s = poller.parse_state(H_PERCENT, NOW)
        self.assertIsNone(s["seven_d"]["utilization"])

    def test_bad_utilization_value_raises_parse_error(self):
        bad = {"anthropic-ratelimit-unified-5h-utilization": "not-a-number"}
        with self.assertRaises(poller.PollerError) as cm:
            poller.parse_state(bad, NOW)
        self.assertEqual(cm.exception.etype, "parse")

    def test_real_headers_full_set(self):
        """실측 12개 헤더: 부가 헤더가 파싱을 깨지 않고, 집계 키가 window 매칭을 오염시키지 않는다."""
        s = poller.parse_state(H_REAL, NOW)
        self.assertTrue(s["ok"])
        self.assertEqual(s["five_h"]["utilization"], 8)
        self.assertEqual(s["seven_d"]["utilization"], 57)
        self.assertEqual(s["five_h"]["resets_at"], 1781276400)
        self.assertEqual(s["status"], "allowed")  # aggregate "status", overage-status 아님


class TestCacheDir(unittest.TestCase):
    def test_linux_xdg(self):
        with mock.patch.object(poller.os, "name", "posix"), \
             mock.patch.object(poller.sys, "platform", "linux"), \
             mock.patch.dict(poller.os.environ, {"XDG_CACHE_HOME": "/x/cache"}):
            self.assertEqual(poller._cache_dir(), os.path.join("/x/cache", "claude-usage"))

    def test_linux_default(self):
        env = {k: v for k, v in poller.os.environ.items() if k != "XDG_CACHE_HOME"}
        with mock.patch.object(poller.os, "name", "posix"), \
             mock.patch.object(poller.sys, "platform", "linux"), \
             mock.patch.dict(poller.os.environ, env, clear=True):
            self.assertEqual(
                poller._cache_dir(),
                os.path.join(os.path.expanduser("~/.cache"), "claude-usage"))

    def test_macos(self):
        with mock.patch.object(poller.os, "name", "posix"), \
             mock.patch.object(poller.sys, "platform", "darwin"):
            self.assertEqual(
                poller._cache_dir(),
                os.path.join(os.path.expanduser("~/Library/Caches"), "claude-usage"))

    def test_windows_localappdata(self):
        with mock.patch.object(poller.os, "name", "nt"), \
             mock.patch.dict(poller.os.environ, {"LOCALAPPDATA": r"C:\Users\u\AppData\Local"}):
            self.assertEqual(
                poller._cache_dir(),
                os.path.join(r"C:\Users\u\AppData\Local", "claude-usage"))

    def test_windows_localappdata_absent_fallback(self):
        env = {k: v for k, v in poller.os.environ.items() if k != "LOCALAPPDATA"}
        with mock.patch.object(poller.os, "name", "nt"), \
             mock.patch.dict(poller.os.environ, env, clear=True):
            self.assertEqual(
                poller._cache_dir(),
                os.path.join(os.path.expanduser(r"~\AppData\Local"), "claude-usage"))


def _http_error(code, headers):
    import email.message
    msg = email.message.Message()
    for k, v in headers.items():
        msg[k] = v
    return urllib.error.HTTPError("https://x", code, "err", msg, io.BytesIO(b""))


class TestCredentials(unittest.TestCase):
    def test_missing_file_is_no_creds(self):
        with mock.patch.object(poller, "CRED_PATH", "/nonexistent/cred.json"):
            with self.assertRaises(poller.PollerError) as cm:
                poller.read_token(NOW)
        self.assertEqual(cm.exception.etype, "no_creds")

    def test_expired_ms_epoch_is_auth_expired(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"claudeAiOauth": {"accessToken": "x",
                                         "expiresAt": (NOW - 60) * 1000}}, f)
        try:
            with mock.patch.object(poller, "CRED_PATH", f.name):
                with self.assertRaises(poller.PollerError) as cm:
                    poller.read_token(NOW)
            self.assertEqual(cm.exception.etype, "auth_expired")
        finally:
            os.unlink(f.name)

    def test_expired_seconds_epoch_is_auth_expired(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"claudeAiOauth": {"accessToken": "x",
                                         "expiresAt": NOW - 60}}, f)
        try:
            with mock.patch.object(poller, "CRED_PATH", f.name):
                with self.assertRaises(poller.PollerError) as cm:
                    poller.read_token(NOW)
            self.assertEqual(cm.exception.etype, "auth_expired")
        finally:
            os.unlink(f.name)


class TestFetch(unittest.TestCase):
    def test_401_raises_auth_expired(self):
        with mock.patch.object(poller.urllib.request, "urlopen",
                               side_effect=_http_error(401, {})):
            with self.assertRaises(poller.PollerError) as cm:
                poller.fetch_headers("tok")
        self.assertEqual(cm.exception.etype, "auth_expired")

    def test_429_returns_headers_and_status(self):
        headers, status = None, None
        with mock.patch.object(poller.urllib.request, "urlopen",
                               side_effect=_http_error(429, H_PERCENT)):
            headers, status = poller.fetch_headers("tok")
        self.assertEqual(status, 429)
        self.assertEqual(
            headers["anthropic-ratelimit-unified-5h-utilization"], "47")


class TestStateFile(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        d = os.path.join(self._tmp.name, "claude-usage")  # 미존재 디렉토리
        self._p1 = mock.patch.object(poller, "STATE_DIR", d)
        self._p2 = mock.patch.object(poller, "STATE_PATH",
                                     os.path.join(d, "state.json"))
        self._p1.start(); self._p2.start()

    def tearDown(self):
        self._p1.stop(); self._p2.stop(); self._tmp.cleanup()

    def test_write_creates_dir_and_reads_back(self):
        state = poller.parse_state(H_PERCENT, NOW)
        poller.write_state(state)
        self.assertEqual(poller.load_prev(), state)

    def test_error_state_preserves_previous_values(self):
        poller.write_state(poller.parse_state(H_PERCENT, NOW))
        err = poller.PollerError("network", "boom")
        s = poller.error_state(err, poller.load_prev(), NOW + 60)
        self.assertFalse(s["ok"])
        self.assertEqual(s["error"]["type"], "network")
        self.assertEqual(s["five_h"]["utilization"], 47)  # 직전 값 보존

    def test_error_state_without_previous(self):
        s = poller.error_state(poller.PollerError("no_creds", "x"), None, NOW)
        self.assertFalse(s["ok"])
        self.assertIsNone(s["five_h"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
