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

    def test_targets_45_through_50(self):
        with open(META) as f:
            m = json.load(f)
        # 45부터 현재 출시된 최신 셸(50)까지 — GNOME 49/50 로드 거부 방지
        self.assertEqual(m["shell-version"], ["45", "46", "47", "48", "49", "50"])


if __name__ == "__main__":
    unittest.main()
