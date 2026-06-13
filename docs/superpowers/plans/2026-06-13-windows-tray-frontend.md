# Windows Tray Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A native Windows system-tray app (.NET / WinForms `NotifyIcon`) that shows the Claude 5-hour usage as a colored tray icon with the percent drawn on it, a hover tooltip, and a context menu (5h/7d/status/refresh/quit).

**Architecture:** Single resident process. The tray app spawns the shared Python core — **frozen to `claude-usage-core.exe` via PyInstaller** so no Python runtime is required on the user's machine — on its own timer (same spawn-and-read-`state.json` pattern as GNOME), then reads `%LOCALAPPDATA%\claude-usage\state.json`. The Windows system tray cannot render inline text, so the percent number is drawn onto the icon bitmap, recolored by threshold. All formatting, color, cadence, and JSON parsing live in a **`net8.0` class library** (`ClaudeUsage.Core`) that is unit-tested with xUnit on Linux/CI; the WinForms shell is a thin `net8.0-windows` layer.

**Tech Stack:** C# / .NET 8, WinForms `NotifyIcon`, System.Drawing (icon rendering), xUnit, PyInstaller (core freeze), the existing shared Python core.

---

# Verification reality

This is the **one frontend the author can fully verify** — they have a Windows machine. But the build is split by where it can run:

- `ClaudeUsage.Core` (logic + JSON) and its xUnit tests target `net8.0` and **build and test on Linux** — `dotnet test` is real coverage runnable in the /orch session and CI (ubuntu).
- `ClaudeUsage.Tray` targets `net8.0-windows` (WinForms) and **only builds/runs on Windows**. The PyInstaller `.exe` likewise must be produced on Windows.
- End-to-end (tray icon renders, polling works, menu acts) is **verified by the author on Windows**, and by a `dotnet build` of the Tray project on a `windows-latest` CI runner.

So: implement and test all logic on Linux; write the Tray shell + freeze script; the author runs the Windows build + live check.

---

# File structure

```text
frontends/windows/
  ClaudeUsageMonitor.sln
  src/ClaudeUsage.Core/
    ClaudeUsage.Core.csproj        ← net8.0, no UI deps
    Models.cs                      ← UsageState / Window / ErrorInfo / UsageColor
    StateReader.cs                 ← read + parse state.json
    Display.cs                     ← format / color / cadence (pure)
  src/ClaudeUsage.Tray/
    ClaudeUsage.Tray.csproj        ← net8.0-windows, WinForms
    Program.cs                     ← entry point
    TrayContext.cs                 ← NotifyIcon + menu + timer + spawn
    IconRenderer.cs                ← draw % onto the tray icon
    app.manifest                   ← per-monitor DPI awareness
  tests/ClaudeUsage.Tests/
    ClaudeUsage.Tests.csproj       ← net8.0, xunit (references Core only)
    DisplayTests.cs
    StateReaderTests.cs
  build-core.ps1                   ← PyInstaller freeze (Windows)
  README.md                        ← build/run/autostart + verification note (rewrite)
.github/workflows/ci.yml           ← MODIFY: dotnet test (ubuntu) + Tray build (windows)
```

---

# Task 1: Core library — models + state reader

**Files:**

- Create: `frontends/windows/ClaudeUsageMonitor.sln`
- Create: `frontends/windows/src/ClaudeUsage.Core/ClaudeUsage.Core.csproj`
- Create: `frontends/windows/src/ClaudeUsage.Core/Models.cs`
- Create: `frontends/windows/src/ClaudeUsage.Core/StateReader.cs`
- Create: `frontends/windows/tests/ClaudeUsage.Tests/ClaudeUsage.Tests.csproj`
- Create: `frontends/windows/tests/ClaudeUsage.Tests/StateReaderTests.cs`

- [ ] **Step 1: Create the solution and projects**

Run (from repo root):

```bash
cd frontends/windows
dotnet new sln -n ClaudeUsageMonitor
dotnet new classlib -n ClaudeUsage.Core -o src/ClaudeUsage.Core -f net8.0
dotnet new xunit -n ClaudeUsage.Tests -o tests/ClaudeUsage.Tests -f net8.0
rm src/ClaudeUsage.Core/Class1.cs tests/ClaudeUsage.Tests/UnitTest1.cs
dotnet sln add src/ClaudeUsage.Core tests/ClaudeUsage.Tests
dotnet add tests/ClaudeUsage.Tests reference src/ClaudeUsage.Core
```

Then set both csproj `PropertyGroup` to include `<Nullable>enable</Nullable>` and `<ImplicitUsings>enable</ImplicitUsings>` (the templates usually do; confirm).

- [ ] **Step 2: Write Models.cs**

```csharp
namespace ClaudeUsage.Core;

public sealed record Window(int? Utilization, long? ResetsAt);

public sealed record ErrorInfo(string? Type, string? Message);

public sealed record UsageState(
    bool Ok,
    long FetchedAt,
    Window? FiveH,
    Window? SevenD,
    string? Status,
    ErrorInfo? Error);

public enum UsageColor { Green, Yellow, Red, Gray }
```

- [ ] **Step 3: Write the failing StateReader tests**

```csharp
// tests/ClaudeUsage.Tests/StateReaderTests.cs
using ClaudeUsage.Core;
using Xunit;

namespace ClaudeUsage.Tests;

public class StateReaderTests
{
    [Fact]
    public void Parse_RealState()
    {
        const string json = """
        {"ok": true, "fetched_at": 1749720000,
         "five_h": {"utilization": 47, "resets_at": 1749730000},
         "seven_d": {"utilization": 12, "resets_at": null},
         "status": "allowed", "error": null}
        """;
        var s = StateReader.Parse(json);
        Assert.NotNull(s);
        Assert.True(s!.Ok);
        Assert.Equal(47, s.FiveH!.Utilization);
        Assert.Equal(1749730000, s.FiveH.ResetsAt);
        Assert.Equal(12, s.SevenD!.Utilization);
        Assert.Null(s.SevenD.ResetsAt);
        Assert.Equal("allowed", s.Status);
        Assert.Null(s.Error);
    }

    [Fact]
    public void Parse_ErrorState()
    {
        const string json = """
        {"ok": false, "fetched_at": 1749720000, "five_h": null, "seven_d": null,
         "status": null, "error": {"type": "network", "message": "boom"}}
        """;
        var s = StateReader.Parse(json);
        Assert.NotNull(s);
        Assert.False(s!.Ok);
        Assert.Equal("network", s.Error!.Type);
        Assert.Null(s.FiveH);
    }

    [Fact]
    public void Parse_InvalidJson_ReturnsNull() => Assert.Null(StateReader.Parse("{not json"));

    [Fact]
    public void Parse_Empty_ReturnsNull() => Assert.Null(StateReader.Parse("  "));

    [Fact]
    public void Read_MissingFile_ReturnsNull()
        => Assert.Null(StateReader.Read("/nonexistent/does-not-exist.json"));
}
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `dotnet test tests/ClaudeUsage.Tests`
Expected: FAIL — `StateReader` does not exist (compile error).

- [ ] **Step 5: Write StateReader.cs**

```csharp
using System.Text.Json;

namespace ClaudeUsage.Core;

public static class StateReader
{
    private static readonly JsonSerializerOptions Opts = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,  // FiveH → five_h
        PropertyNameCaseInsensitive = true,
    };

    /// <summary>state.json 텍스트를 파싱. 비었거나 깨졌으면 null.</summary>
    public static UsageState? Parse(string json)
    {
        if (string.IsNullOrWhiteSpace(json)) return null;
        try { return JsonSerializer.Deserialize<UsageState>(json, Opts); }
        catch (JsonException) { return null; }
    }

    /// <summary>state 파일을 읽어 파싱. 없거나 못 읽으면 null.</summary>
    public static UsageState? Read(string path)
    {
        try { return Parse(File.ReadAllText(path)); }
        catch (IOException) { return null; }
        catch (UnauthorizedAccessException) { return null; }
    }

    /// <summary>%LOCALAPPDATA%\claude-usage\state.json — 코어의 _cache_dir(Windows)과 일치.</summary>
    public static string DefaultPath()
    {
        var local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        return Path.Combine(local, "claude-usage", "state.json");
    }
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `dotnet test tests/ClaudeUsage.Tests`
Expected: PASS (5 tests).

- [ ] **Step 7: Commit**

```bash
git add frontends/windows/ClaudeUsageMonitor.sln frontends/windows/src/ClaudeUsage.Core frontends/windows/tests/ClaudeUsage.Tests
git commit -m "feat(windows): Core library — state.json models and reader with xUnit tests"
```

---

# Task 2: Core library — display, color, cadence

The full display policy, mirroring `extension.js` and the macOS `usage_display.py`. No UI types — `ColorFor` returns the `UsageColor` enum so the Tray maps it to a `System.Drawing.Color`. This keeps the library `net8.0`-pure and Linux-testable.

**Files:**

- Create: `frontends/windows/src/ClaudeUsage.Core/Display.cs`
- Create: `frontends/windows/tests/ClaudeUsage.Tests/DisplayTests.cs`

- [ ] **Step 1: Write the failing DisplayTests**

```csharp
// tests/ClaudeUsage.Tests/DisplayTests.cs
using ClaudeUsage.Core;
using Xunit;

namespace ClaudeUsage.Tests;

public class DisplayTests
{
    private const long Now = 1_749_700_000;

    private static UsageState State(Window? five = null, Window? seven = null,
        bool ok = true, ErrorInfo? error = null, string? status = "allowed", long fetched = Now)
        => new(ok, fetched, five, seven, status, error);

    [Theory]
    [InlineData(0, "0m")]
    [InlineData(12 * 60, "12m")]
    public void FormatRemaining_MinutesOnly(long delta, string expected)
        => Assert.Equal(expected, Display.FormatRemaining(Now + delta, Now));

    [Fact]
    public void FormatRemaining_HoursZeroPadded()
        => Assert.Equal("3h05m", Display.FormatRemaining(Now + 3 * 3600 + 5 * 60, Now));

    [Fact]
    public void FormatRemaining_PastClampsToZero()
        => Assert.Equal("0m", Display.FormatRemaining(Now - 100, Now));

    [Theory]
    [InlineData(59, UsageColor.Green)]
    [InlineData(60, UsageColor.Yellow)]
    [InlineData(84, UsageColor.Yellow)]
    [InlineData(85, UsageColor.Red)]
    public void ColorForPct_Thresholds(int pct, UsageColor expected)
        => Assert.Equal(expected, Display.ColorForPct(pct));

    [Fact]
    public void IconText_Normal_IsPercentNumber()
        => Assert.Equal("47", Display.IconText(State(new Window(47, Now + 3600)), Now));

    [Fact]
    public void IconText_LoginNeeded_IsBang()
        => Assert.Equal("!", Display.IconText(
            State(ok: false, error: new ErrorInfo("no_creds", "x")), Now));

    [Fact]
    public void IconText_NoState_IsEllipsis()
        => Assert.Equal("…", Display.IconText(null, Now));

    [Fact]
    public void ColorFor_RateLimited_IsRed()
        => Assert.Equal(UsageColor.Red, Display.ColorFor(
            State(new Window(30, null), error: new ErrorInfo("rate_limited", "x")), Now));

    [Fact]
    public void ColorFor_StaleWithError_IsGray()
        => Assert.Equal(UsageColor.Gray, Display.ColorFor(
            State(new Window(30, null), ok: false, error: new ErrorInfo("network", "x")), Now));

    [Fact]
    public void Menu5h_WithReset()
        => Assert.Equal("5시간 창  47% 사용 · 3h12m 후 리셋",
            Display.Menu5h(State(new Window(47, Now + 3 * 3600 + 12 * 60)), Now));

    [Fact]
    public void Menu7d_Absent() => Assert.Equal("7일 창  —", Display.Menu7d(State()));

    [Fact]
    public void MenuMeta_Error()
        => Assert.Equal("오류: network · 2분 전 갱신",
            Display.MenuMeta(State(error: new ErrorInfo("network", "x"), fetched: Now - 120), Now));

    [Fact]
    public void NextInterval_FastWithinWindow()
        => Assert.Equal(Display.FastSeconds,
            Display.NextInterval(State(new Window(90, Now + 600)), Now));

    [Fact]
    public void NextInterval_NormalFarOff()
        => Assert.Equal(Display.NormalSeconds,
            Display.NextInterval(State(new Window(10, Now + 4 * 3600)), Now));
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `dotnet test tests/ClaudeUsage.Tests`
Expected: FAIL — `Display` does not exist.

- [ ] **Step 3: Write Display.cs**

```csharp
namespace ClaudeUsage.Core;

public static class Display
{
    public const int NormalSeconds = 600;       // 평소 폴링 간격
    public const int FastSeconds = 60;           // 리셋 임박 폴링 간격
    public const int FastWindowSeconds = 1800;   // 리셋 30분 전부터 가속

    public static string FormatRemaining(long resetsAt, long now)
    {
        var s = Math.Max(0, resetsAt - now);
        var h = s / 3600;
        var m = (s % 3600) / 60;
        return h > 0 ? $"{h}h{m:D2}m" : $"{m}m";
    }

    public static UsageColor ColorForPct(int pct) =>
        pct >= 85 ? UsageColor.Red : pct >= 60 ? UsageColor.Yellow : UsageColor.Green;

    private static string? ErrType(UsageState? s) => s?.Error?.Type;

    private static Window? Five(UsageState? s) =>
        s?.FiveH is { Utilization: not null } f ? f : null;

    public static UsageColor ColorFor(UsageState? state, long now)
    {
        if (state is null) return UsageColor.Gray;
        var err = ErrType(state);
        if (err is "no_creds" or "auth_expired") return UsageColor.Gray;
        var f = Five(state);
        if (f is null) return UsageColor.Gray;
        if (err == "rate_limited") return UsageColor.Red;
        if (!state.Ok) return UsageColor.Gray;          // 오래된 값 + 오류
        return ColorForPct(f.Utilization!.Value);
    }

    /// <summary>트레이 아이콘에 그릴 짧은 텍스트: 퍼센트 숫자, 또는 센티넬.</summary>
    public static string IconText(UsageState? state, long now)
    {
        if (state is null) return "…";
        var err = ErrType(state);
        if (err is "no_creds" or "auth_expired") return "!";
        var f = Five(state);
        return f is null ? "…" : f.Utilization!.Value.ToString();
    }

    public static string Tooltip(UsageState? state, long now)
    {
        if (state is null) return "Claude Usage — 아직 데이터 없음";
        var err = ErrType(state);
        if (err is "no_creds" or "auth_expired") return "Claude Usage — 로그인 필요";
        var f = Five(state);
        if (f is null) return "Claude Usage — …";
        var remain = f.ResetsAt is { } r ? $" · {FormatRemaining(r, now)} 후 리셋" : "";
        var seven = state.SevenD is { Utilization: not null } d ? $"\n7일: {d.Utilization}%" : "";
        return $"Claude 5시간: {f.Utilization}%{remain}{seven}";
    }

    public static string Menu5h(UsageState? state, long now)
    {
        var f = Five(state);
        if (f is null) return "5시간 창  —";
        var suffix = f.ResetsAt is { } r ? $" · {FormatRemaining(r, now)} 후 리셋" : "";
        return $"5시간 창  {f.Utilization}% 사용{suffix}";
    }

    public static string Menu7d(UsageState? state)
    {
        if (state?.SevenD is { Utilization: not null } d) return $"7일 창  {d.Utilization}% 사용";
        return "7일 창  —";
    }

    public static string MenuMeta(UsageState? state, long now)
    {
        if (state is null) return "아직 데이터 없음";
        var age = Math.Max(0, now - state.FetchedAt);
        var ageTxt = age < 60 ? "방금" : $"{age / 60}분 전";
        var err = ErrType(state);
        return err is not null
            ? $"오류: {err} · {ageTxt} 갱신"
            : $"상태: {state.Status ?? "OK"} · {ageTxt} 갱신";
    }

    public static int NextInterval(UsageState? state, long now)
    {
        if (state?.FiveH?.ResetsAt is { } r)
        {
            var remain = r - now;
            if (remain > 0 && remain <= FastWindowSeconds) return FastSeconds;
        }
        return NormalSeconds;
    }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `dotnet test tests/ClaudeUsage.Tests`
Expected: PASS (Task 1 + Task 2 tests, ~22 total).

- [ ] **Step 5: Commit**

```bash
git add frontends/windows/src/ClaudeUsage.Core/Display.cs frontends/windows/tests/ClaudeUsage.Tests/DisplayTests.cs
git commit -m "feat(windows): Core display/color/cadence logic with full xUnit coverage"
```

---

# Task 3: Freeze the shared core to an exe

PyInstaller bundles `claude_usage_core.py` and a Python runtime into one `claude-usage-core.exe`, so the target machine needs no Python. `--noconsole` prevents a console window flashing on each poll. **Runs on Windows** (PyInstaller emits a native exe for the OS it runs on).

**Files:**

- Create: `frontends/windows/build-core.ps1`

- [ ] **Step 1: Write build-core.ps1**

```powershell
# build-core.ps1 — 공유 코어를 단일 exe로 동결 (Windows에서 실행)
#   pip install pyinstaller
#   ./build-core.ps1
$ErrorActionPreference = "Stop"
$core = Join-Path $PSScriptRoot "..\..\core\claude_usage_core.py"
pyinstaller --onefile --noconsole --name claude-usage-core $core
Write-Host "built: $(Join-Path $PSScriptRoot 'dist\claude-usage-core.exe')"
Write-Host "이 exe를 Tray publish 출력 폴더(앱 .exe 옆)에 복사한다."
```

- [ ] **Step 2: Verify on Windows**

Run (Windows, with credentials present):

```powershell
pip install pyinstaller
./build-core.ps1
./dist/claude-usage-core.exe
Get-Content "$env:LOCALAPPDATA\claude-usage\state.json"
```

Expected: the exe runs silently and writes a valid `state.json` (`"ok": true` with a `five_h.utilization`). This confirms `_cache_dir()` resolves to `%LOCALAPPDATA%\claude-usage` on Windows.

> This step cannot be verified in the Linux /orch session — PyInstaller on Linux produces an ELF binary, not a `.exe`. Mark it for the author's Windows pass.

- [ ] **Step 3: Commit**

```bash
git add frontends/windows/build-core.ps1
git commit -m "build(windows): PyInstaller freeze script for the shared core"
```

---

# Task 4: WinForms tray shell

The resident UI. It owns no formatting — every string and color comes from `ClaudeUsage.Core`. A `System.Windows.Forms.Timer` (UI thread) ticks every 5 s: re-read `state.json`, schedule a poll by `NextInterval`, and re-render. A poll spawns `claude-usage-core.exe` (hidden, no console), guarded against overlap. The percent is drawn onto the icon by `IconRenderer`.

> **Windows-only:** `net8.0-windows` + WinForms builds and runs on Windows only. Written here, built and verified by the author.

**Files:**

- Create: `frontends/windows/src/ClaudeUsage.Tray/ClaudeUsage.Tray.csproj`
- Create: `frontends/windows/src/ClaudeUsage.Tray/app.manifest`
- Create: `frontends/windows/src/ClaudeUsage.Tray/Program.cs`
- Create: `frontends/windows/src/ClaudeUsage.Tray/IconRenderer.cs`
- Create: `frontends/windows/src/ClaudeUsage.Tray/TrayContext.cs`

- [ ] **Step 1: Create the Tray project and wire references**

Run:

```bash
cd frontends/windows
dotnet new winforms -n ClaudeUsage.Tray -o src/ClaudeUsage.Tray -f net8.0-windows
rm src/ClaudeUsage.Tray/Form1.cs src/ClaudeUsage.Tray/Form1.Designer.cs 2>/dev/null || true
dotnet sln add src/ClaudeUsage.Tray
dotnet add src/ClaudeUsage.Tray reference src/ClaudeUsage.Core
```

- [ ] **Step 2: Set ClaudeUsage.Tray.csproj**

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>WinExe</OutputType>
    <TargetFramework>net8.0-windows</TargetFramework>
    <UseWindowsForms>true</UseWindowsForms>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <ApplicationManifest>app.manifest</ApplicationManifest>
    <AssemblyName>ClaudeUsageMonitor</AssemblyName>
  </PropertyGroup>
  <ItemGroup>
    <ProjectReference Include="..\ClaudeUsage.Core\ClaudeUsage.Core.csproj" />
  </ItemGroup>
</Project>
```

- [ ] **Step 3: Write app.manifest (crisp icon on high-DPI)**

```xml
<?xml version="1.0" encoding="utf-8"?>
<assembly manifestVersion="1.0" xmlns="urn:schemas-microsoft-com:asm.v1">
  <application xmlns="urn:schemas-microsoft-com:asm.v3">
    <windowsSettings>
      <dpiAwareness xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">PerMonitorV2</dpiAwareness>
    </windowsSettings>
  </application>
</assembly>
```

- [ ] **Step 4: Write Program.cs**

```csharp
namespace ClaudeUsage.Tray;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        ApplicationConfiguration.Initialize();
        Application.Run(new TrayContext());
    }
}
```

- [ ] **Step 5: Write IconRenderer.cs**

```csharp
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Drawing.Text;
using ClaudeUsage.Core;

namespace ClaudeUsage.Tray;

public static class IconRenderer
{
    private static Color ToColor(UsageColor c) => c switch
    {
        UsageColor.Green => Color.FromArgb(0x57, 0xe3, 0x89),
        UsageColor.Yellow => Color.FromArgb(0xf8, 0xe4, 0x5c),
        UsageColor.Red => Color.FromArgb(0xff, 0x6b, 0x6b),
        _ => Color.FromArgb(0x9a, 0x99, 0x96),
    };

    /// <summary>퍼센트 숫자를 색 원 위에 그려 트레이 아이콘 생성. 호출자가 Icon과 HICON을 해제.</summary>
    public static Icon Render(string text, UsageColor color)
    {
        const int size = 32;  // 고해상도; Windows가 트레이에 맞게 다운스케일
        using var bmp = new Bitmap(size, size, PixelFormat.Format32bppArgb);
        using (var g = Graphics.FromImage(bmp))
        {
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.TextRenderingHint = TextRenderingHint.AntiAliasGridFit;
            g.Clear(Color.Transparent);
            using var bg = new SolidBrush(ToColor(color));
            g.FillEllipse(bg, 0, 0, size - 1, size - 1);

            var fontSize = text.Length >= 3 ? 11f : 15f;  // "100"은 작게, "47"/"!"는 크게
            using var font = new Font("Segoe UI", fontSize, FontStyle.Bold, GraphicsUnit.Pixel);
            using var fg = new SolidBrush(Color.Black);
            using var fmt = new StringFormat
            {
                Alignment = StringAlignment.Center,
                LineAlignment = StringAlignment.Center,
            };
            g.DrawString(text, font, fg, new RectangleF(0, 0, size, size), fmt);
        }
        return Icon.FromHandle(bmp.GetHicon());  // HICON은 TrayContext가 DestroyIcon으로 해제
    }
}
```

- [ ] **Step 6: Write TrayContext.cs**

```csharp
using System.Diagnostics;
using System.Runtime.InteropServices;
using ClaudeUsage.Core;

namespace ClaudeUsage.Tray;

public sealed class TrayContext : ApplicationContext
{
    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool DestroyIcon(IntPtr handle);

    private const int TickMs = 5000;        // 결과 수거 + 폴링 스케줄 + 카운트다운 재계산
    private const int PollGuardMs = 8000;   // 코어 exe 강제 종료 한도

    private readonly NotifyIcon _icon;
    private readonly ToolStripMenuItem _row5h = new("5시간 창  —") { Enabled = false };
    private readonly ToolStripMenuItem _row7d = new("7일 창  —") { Enabled = false };
    private readonly ToolStripMenuItem _rowMeta = new("갱신 전") { Enabled = false };
    private readonly System.Windows.Forms.Timer _timer = new() { Interval = TickMs };
    private readonly string _statePath = StateReader.DefaultPath();
    private readonly string _coreExe = Path.Combine(AppContext.BaseDirectory, "claude-usage-core.exe");

    private UsageState? _state;
    private long _nextPollAt;          // 0 = 즉시 폴링
    private Process? _pollProc;
    private IntPtr _lastHicon = IntPtr.Zero;

    public TrayContext()
    {
        var refresh = new ToolStripMenuItem("지금 갱신", null, (_, _) => _nextPollAt = 0);
        var quit = new ToolStripMenuItem("종료", null, (_, _) => ExitThread());
        var menu = new ContextMenuStrip();
        menu.Items.AddRange(new ToolStripItem[]
        {
            _row5h, _row7d, new ToolStripSeparator(), _rowMeta, refresh, quit,
        });

        _icon = new NotifyIcon { Visible = true, ContextMenuStrip = menu, Text = "Claude Usage" };

        _state = StateReader.Read(_statePath);
        Render();

        _timer.Tick += (_, _) => OnTick();
        _timer.Start();
    }

    private static long Now() => DateTimeOffset.UtcNow.ToUnixTimeSeconds();

    private void OnTick()
    {
        var now = Now();
        var fresh = StateReader.Read(_statePath);
        if (fresh is not null) _state = fresh;

        if (now >= _nextPollAt && (_pollProc is null || _pollProc.HasExited))
            LaunchPoll(now);

        Render();
    }

    private void LaunchPoll(long now)
    {
        _nextPollAt = now + Display.NextInterval(_state, now);
        if (!File.Exists(_coreExe)) return;   // 코어 exe 미동봉 → 조용히 스킵
        try
        {
            _pollProc = Process.Start(new ProcessStartInfo(_coreExe)
            {
                CreateNoWindow = true,
                UseShellExecute = false,
                WindowStyle = ProcessWindowStyle.Hidden,
            });
            if (_pollProc is not null)
            {
                _pollProc.EnableRaisingEvents = true;
                var guard = new System.Windows.Forms.Timer { Interval = PollGuardMs };
                guard.Tick += (_, _) =>
                {
                    guard.Stop(); guard.Dispose();
                    try { if (_pollProc is { HasExited: false }) _pollProc.Kill(); }
                    catch { /* 이미 종료됨 */ }
                };
                guard.Start();
            }
        }
        catch (Exception)
        {
            _pollProc = null;  // spawn 실패 → 기존 state.json 그대로 표시
        }
    }

    private void Render()
    {
        var now = Now();
        var color = Display.ColorFor(_state, now);
        var oldIcon = _icon.Icon;
        var oldHicon = _lastHicon;

        var newIcon = IconRenderer.Render(Display.IconText(_state, now), color);
        _icon.Icon = newIcon;
        _lastHicon = newIcon.Handle;
        oldIcon?.Dispose();
        if (oldHicon != IntPtr.Zero) DestroyIcon(oldHicon);  // FromHandle은 HICON을 소유 안 함

        _icon.Text = Truncate(Display.Tooltip(_state, now), 127);  // NotifyIcon.Text 한도
        _row5h.Text = Display.Menu5h(_state, now);
        _row7d.Text = Display.Menu7d(_state);
        _rowMeta.Text = Display.MenuMeta(_state, now);
    }

    private static string Truncate(string s, int max) => s.Length <= max ? s : s[..max];

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            _timer.Dispose();
            _icon.Visible = false;
            var hicon = _lastHicon;
            _icon.Icon?.Dispose();
            _icon.Dispose();
            if (hicon != IntPtr.Zero) DestroyIcon(hicon);
        }
        base.Dispose(disposing);
    }
}
```

- [ ] **Step 7: Build on Windows and eyeball it**

Run (Windows):

```powershell
dotnet build src/ClaudeUsage.Tray -c Debug
# build-core.ps1을 먼저 돌려 dist\claude-usage-core.exe를 만든 뒤,
# bin\Debug\net8.0-windows\ 로 복사하고 ClaudeUsageMonitor.exe 실행
```

Author verifies: a colored circle with the percent appears in the tray; hover shows the tooltip; right-click shows 5h/7d/status/refresh/quit; "지금 갱신" updates within ~5 s; color matches usage.

> Build is verified in CI on a `windows-latest` runner (Task 6). Runtime appearance is the author's manual check.

- [ ] **Step 8: Commit**

```bash
git add frontends/windows/src/ClaudeUsage.Tray
git commit -m "feat(windows): WinForms tray shell — NotifyIcon, percent-on-icon, poll timer"
```

---

# Task 5: Packaging + autostart + README

**Files:**

- Modify: `frontends/windows/README.md`

- [ ] **Step 1: Rewrite frontends/windows/README.md**

````markdown
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
````

- [ ] **Step 2: Commit**

```bash
git add frontends/windows/README.md
git commit -m "docs(windows): build, packaging, autostart, and verification README"
```

---

# Task 6: CI — dotnet test (Linux) + Tray build (Windows)

**Files:**

- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add two jobs**

```yaml
  windows-core-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-dotnet@v4
        with:
          dotnet-version: "8.0.x"
      - name: Test the Core library (net8.0 — runs on Linux)
        working-directory: frontends/windows
        run: dotnet test tests/ClaudeUsage.Tests -c Release

  windows-tray-build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-dotnet@v4
        with:
          dotnet-version: "8.0.x"
      - name: Build the WinForms tray (net8.0-windows)
        working-directory: frontends/windows
        run: dotnet build src/ClaudeUsage.Tray -c Release
```

> The Linux job tests only the test project (which references Core only), so it never tries to build the `net8.0-windows` Tray project on Linux.

- [ ] **Step 2: Verify the Linux test job locally (if the .NET SDK is available)**

Run: `cd frontends/windows && dotnet test tests/ClaudeUsage.Tests`
Expected: PASS (~22 tests). If the SDK is absent in the session, rely on CI.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci(windows): dotnet test on ubuntu and Tray build on windows runner"
```

---

# Final review

After all tasks, dispatch a final reviewer over `frontends/windows/`. Verify:

- `dotnet test frontends/windows/tests/ClaudeUsage.Tests` — all pass.
- No formatting/color/cadence logic lives in the Tray project — all of it in `ClaudeUsage.Core`.
- `state.json` path in C# (`%LOCALAPPDATA%\claude-usage`) matches the core's `_cache_dir()` for Windows.

Then the author runs the Windows build (`build-core.ps1` + `dotnet publish`) and confirms the live tray. Hand off via superpowers:finishing-a-development-branch; update `ARCHITECTURE.md` (Windows row → "동작, 작성자 실기 검증") and the project memory.
