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
