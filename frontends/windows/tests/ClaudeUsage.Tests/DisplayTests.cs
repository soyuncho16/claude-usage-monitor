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
