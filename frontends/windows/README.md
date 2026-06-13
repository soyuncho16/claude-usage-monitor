# Windows frontend

Windows 시스템 트레이 앱 (.NET 8 / WinForms). 트레이 아이콘에 5시간 사용률 퍼센트를
임계값 색(녹/황/적/회)으로 그려 표시하고, 호버하면 툴팁, 우클릭하면 5시간/7일/상태/지금
갱신/종료 메뉴를 연다. 트레이는 인라인 텍스트를 못 그리므로 퍼센트를 아이콘에 직접
그린다. 단일 프로세스로, 동결된 공유 코어(`claude-usage-core.exe`)를 자체 타이머로
spawn해 `%LOCALAPPDATA%\claude-usage\state.json`을 읽는다(10분 주기, 리셋 30분 전부터 1분).

## 빌드 (Windows)

```powershell
# 1) 공유 코어를 exe로 동결
pip install pyinstaller
./build-core.ps1

# 2) 트레이 앱 publish (단일 파일, 자체 포함)
dotnet publish src/ClaudeUsage.Tray -c Release -r win-x64 --self-contained `
    -p:PublishSingleFile=true -o publish

# 3) 코어 exe를 앱 옆에 둔다
Copy-Item dist/claude-usage-core.exe publish/
```

`publish/ClaudeUsageMonitor.exe`를 실행하면 트레이에 뜬다. `~/.claude/.credentials.json`의
OAuth 토큰을 읽으므로 Claude Code 로그인이 되어 있어야 한다.

## 자동 시작 (선택)

시작 폴더에 바로가기를 만든다:

```powershell
$startup = [Environment]::GetFolderPath('Startup')
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut("$startup\Claude Usage Monitor.lnk")
$lnk.TargetPath = (Resolve-Path publish/ClaudeUsageMonitor.exe).Path
$lnk.Save()
```

## 검증 현황

> 세 프론트엔드 중 **작성자가 실기로 검증 가능한 유일한** 플랫폼이다. 로직(`ClaudeUsage.Core`)은
> Linux/CI에서 `dotnet test`로 검증되고, WinForms 트레이 셸은 작성자가 Windows에서 직접
> 빌드·실행·확인한다(아이콘 렌더·폴링·메뉴 동작).
