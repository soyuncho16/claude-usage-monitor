# build-core.ps1 — 공유 코어를 단일 exe로 동결 (Windows에서 실행)
#   pip install pyinstaller
#   ./build-core.ps1
$ErrorActionPreference = "Stop"
$core = Join-Path $PSScriptRoot "..\..\core\claude_usage_core.py"
pyinstaller --onefile --noconsole --name claude-usage-core $core
Write-Host "built: $(Join-Path $PSScriptRoot 'dist\claude-usage-core.exe')"
Write-Host "이 exe를 Tray publish 출력 폴더(앱 .exe 옆)에 복사한다."
