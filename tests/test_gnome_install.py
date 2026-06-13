"""install.sh 패키징 계약을 오프라인으로 검증한다.

install.sh가 복사하는 파일이 실재하지 않으면 설치는 런타임에서야 깨진다.
이 테스트는 셸 실행·네트워크 없이 그 계약을 게이트로 끌어올린다 (CI 코어 잡에서 통과).
"""
import json
import os
import re
import unittest

HERE = os.path.dirname(__file__)
GNOME = os.path.join(HERE, "..", "frontends", "gnome")
REPO = os.path.join(HERE, "..")
INSTALL = os.path.join(GNOME, "install.sh")
META = os.path.join(GNOME, "metadata.json")


class TestGnomeInstall(unittest.TestCase):
    def setUp(self):
        with open(INSTALL) as f:
            self.script = f.read()

    def test_copies_existing_frontend_files(self):
        # install.sh가 $HERE/<file>로 복사하는 프론트엔드 파일은 모두 실재해야 한다
        # (확장자 있는 파일명만 — `$HERE/../..` 같은 경로 토큰은 제외)
        names = re.findall(r"\$HERE/([\w-]+\.\w+)", self.script)
        self.assertIn("extension.js", names)
        for name in names:
            self.assertTrue(
                os.path.isfile(os.path.join(GNOME, name)),
                f"install.sh가 복사하는 {name}이(가) frontends/gnome에 없음")

    def test_copies_existing_core(self):
        # $REPO/<path>로 복사하는 공유 코어 스크립트도 실재해야 한다
        paths = re.findall(r"\$REPO/([\w./]+)", self.script)
        self.assertIn("core/claude_usage_core.py", paths)
        for p in paths:
            self.assertTrue(
                os.path.isfile(os.path.join(REPO, p)),
                f"install.sh가 복사하는 {p}이(가) repo에 없음")

    def test_uuid_matches_metadata(self):
        # 설치 디렉토리 UUID는 metadata.json의 uuid와 일치해야 한다
        with open(META) as f:
            m = json.load(f)
        uuid = re.search(r'UUID="([^"]+)"', self.script).group(1)
        self.assertEqual(uuid, m["uuid"])


if __name__ == "__main__":
    unittest.main()
