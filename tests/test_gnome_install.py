"""install.sh 패키징 계약을 오프라인으로 검증한다.

install.sh가 복사하는 파일이 실재하지 않으면 설치는 런타임에서야 깨진다.
이 테스트는 셸 실행·네트워크 없이 그 계약을 게이트로 끌어올린다 (CI 코어 잡에서 통과).
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(__file__)
GNOME = os.path.join(HERE, "..", "frontends", "gnome")
REPO = os.path.join(HERE, "..")
INSTALL = os.path.join(GNOME, "install.sh")
META = os.path.join(GNOME, "metadata.json")

UUID = "claude-usage-monitor@soyuncho16.github.io"
INSTALLED_REL = os.path.join(
    ".local", "share", "gnome-shell", "extensions", UUID)


class TestGnomeInstall(unittest.TestCase):
    def setUp(self):
        with open(INSTALL) as f:
            self.script = f.read()

    def test_copies_existing_frontend_files(self):
        # install.sh가 $HERE/<file>로 복사하는 프론트엔드 파일은 모두 실재해야 한다
        # (확장자 있는 파일명만 — `$HERE/../..` 같은 경로 토큰은 제외)
        names = re.findall(r"\$HERE/([\w-]+\.\w+)", self.script)
        # 런타임에 반드시 필요한 프론트엔드 파일은 install.sh가 하나라도 빠뜨리면 안 된다
        for required in ("extension.js", "metadata.json", "stylesheet.css"):
            self.assertIn(required, names,
                          f"install.sh가 런타임 필수 파일 {required}을(를) 복사하지 않음")
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


@unittest.skipIf(os.name == "nt", "install.sh는 POSIX 셸 스크립트 (Windows 미해당)")
@unittest.skipUnless(shutil.which("bash"), "bash가 있어야 install.sh를 실행한다")
class TestGnomeStagedInstall(unittest.TestCase):
    """install.sh를 임시 HOME에 실제로 실행해 설치 결과를 검증한다.

    정규식 파싱 테스트가 놓치는 것 — cp 인자가 멀쩡해도 셸 실행이 실패하거나,
    설치 디렉토리에 예상 외 파일이 남는 경우 — 를 end-to-end로 잡는다.
    """

    def test_install_stages_exact_runtime_file_set(self):
        with tempfile.TemporaryDirectory() as home:
            env = dict(os.environ, HOME=home)
            r = subprocess.run(
                ["bash", os.path.abspath(INSTALL)],
                env=env, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)

            dst = os.path.join(home, INSTALLED_REL)
            self.assertTrue(os.path.isdir(dst), f"설치 디렉토리 미생성: {dst}")
            installed = sorted(os.listdir(dst))
            # 런타임에 필요한 정확한 파일 집합 — 더도 덜도 아님
            self.assertEqual(installed, [
                "claude_usage_core.py",  # 공유 코어 (REPO/core에서 복사)
                "extension.js",
                "metadata.json",
                "stylesheet.css",
            ])


if __name__ == "__main__":
    unittest.main()
