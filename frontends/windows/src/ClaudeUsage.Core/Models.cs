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
