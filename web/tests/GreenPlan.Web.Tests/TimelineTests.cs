using System.Net;
using System.Text.Json;
using GreenPlan.Web.Models;
using GreenPlan.Web.Presentation;
using GreenPlan.Web.Tests.Support;

namespace GreenPlan.Web.Tests;

public sealed class TimelineTests
{
    private static readonly DateTimeOffset Now = new(2026, 9, 25, 10, 0, 0, TimeSpan.Zero);

    private static JobDto RunningOnPlacement() =>
        TestJobs.Running() with
        {
            Stage = "place_plants",
            StartedAt = "2026-09-25T09:59:08+00:00",
            StageStartedAt = "2026-09-25T09:59:18+00:00",
            StageTimings = new Dictionary<string, double> { ["read_drawings"] = 9.14, ["recognize_site"] = 0.7 },
        };

    [Fact]
    public void MissingBenefitIsLeftOutInsteadOfADash()
    {
        var summary = new JobSummaryView(new Dictionary<string, JsonElement>
        {
            ["benefits"] = JsonSerializer.SerializeToElement(new { street_front_share = 0.137, sidewalk_shade_share = (double?)null, open_lawn_share = 0.874 }),
        });

        Assert.Equal("проезжая часть отделена посадками на 14 % фронта; открытый газон — 87 %", summary.BenefitText());
    }

    [Theory]
    [InlineData(12.34, "12,3 с")]
    [InlineData(9.0, "9 с")]
    [InlineData(75.0, "1 мин 15 с")]
    [InlineData(3725.0, "1 ч 02 мин")]
    public void DurationsAreReadable(double seconds, string expected)
    {
        Assert.Equal(expected, DurationText.For(seconds));
    }

    [Fact]
    public void RunningJobShowsFinishedCurrentAndPendingStages()
    {
        var timeline = JobTimeline.From(RunningOnPlacement(), Now);
        var states = timeline.Stages.ToDictionary(stage => stage.Key, stage => stage.State);

        Assert.Equal(StageStates.Done, states["read_drawings"]);
        Assert.Equal(StageStates.Current, states["place_plants"]);
        Assert.Equal(StageStates.Pending, states["verify"]);
        Assert.Equal(42.0, timeline.Stages.Single(stage => stage.Key == "place_plants").Seconds);
        Assert.Equal(52.0, timeline.ElapsedSeconds);
    }

    [Fact]
    public void FailedStageKeepsItsTime()
    {
        var job = RunningOnPlacement() with
        {
            Status = JobStatuses.Failed,
            FinishedAt = "2026-09-25T09:59:48+00:00",
        };

        var timeline = JobTimeline.From(job, Now);

        var failed = timeline.Stages.Single(stage => stage.Key == "place_plants");
        Assert.Equal(StageStates.Failed, failed.State);
        Assert.Equal(30.0, failed.Seconds);
        Assert.Equal(40.0, timeline.ElapsedSeconds);
    }

    [Fact]
    public void OlderFinishedJobsTakeTimesFromTheSummary()
    {
        var timeline = JobTimeline.From(TestJobs.Succeeded(), Now);

        Assert.Equal(88.4, timeline.Stages.Single(stage => stage.Key == "read_drawings").Seconds);
        Assert.Equal(StageStates.Done, timeline.Stages.Single(stage => stage.Key == "verify").State);
        Assert.Null(timeline.ElapsedSeconds);
    }

    [Fact]
    public async Task JobPageListsStagesWithTimesAndTotal()
    {
        using var factory = new GreenPlanWebFactory { Clock = { Now = Now } };
        factory.Engine.Jobs.Add(RunningOnPlacement());
        using var client = factory.CreateClient();

        var html = await client.GetStringAsync($"/Jobs/Details/{TestJobs.RunningId}");

        Assert.Contains("Ход расчёта", html);
        Assert.Contains("9,1 с", html);
        Assert.Contains("class=\"stage stage-current\" data-stage=\"place_plants\"", html);
        Assert.Contains("42 с", html);
        Assert.Contains("Всего", html);
        Assert.Contains("52 с", html);
    }

    [Fact]
    public async Task StatusEndpointCarriesStagesAndElapsedTime()
    {
        using var factory = new GreenPlanWebFactory { Clock = { Now = Now } };
        factory.Engine.Jobs.Add(RunningOnPlacement());
        using var client = factory.CreateClient();

        using var response = await client.GetAsync($"/jobs/{TestJobs.RunningId}/status");
        using var status = JsonDocument.Parse(await response.Content.ReadAsStringAsync());

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var stages = status.RootElement.GetProperty("stages").EnumerateArray().ToList();
        Assert.Equal(StageNames.Count, stages.Count);
        Assert.Equal("current", stages[2].GetProperty("state").GetString());
        Assert.Equal("42 с", stages[2].GetProperty("timeText").GetString());
        Assert.Equal(52.0, status.RootElement.GetProperty("elapsedSeconds").GetDouble());
    }
}
