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
