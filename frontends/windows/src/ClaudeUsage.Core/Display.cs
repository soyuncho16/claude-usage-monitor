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
