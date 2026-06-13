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
