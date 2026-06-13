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
