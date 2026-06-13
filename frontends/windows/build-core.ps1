# build-core.ps1 — 공유 코어를 단일 exe로 동결 (Windows에서 실행)
#   pip install -r requirements-build.txt   # pyinstaller 버전 고정
#   ./build-core.ps1
$ErrorActionPreference = "Stop"
$core = Join-Path $PSScriptRoot "..\..\core\claude_usage_core.py"
# 출력 경로를 스크립트 디렉터리에 고정 — 어디서 호출해도 dist/build/spec가 여기에 생긴다.
pyinstaller --onefile --noconsole --name claude-usage-core `
    --distpath (Join-Path $PSScriptRoot "dist") `
    --workpath (Join-Path $PSScriptRoot "build") `
    --specpath $PSScriptRoot `
    $core
Write-Host "built: $(Join-Path $PSScriptRoot 'dist\claude-usage-core.exe')"
Write-Host "이 exe를 Tray publish 출력 폴더(앱 .exe 옆)에 복사한다."
