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
