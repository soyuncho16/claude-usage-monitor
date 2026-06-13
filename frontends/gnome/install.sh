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
