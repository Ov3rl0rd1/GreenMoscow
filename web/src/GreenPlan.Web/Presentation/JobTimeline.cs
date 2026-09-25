using System.Globalization;
using GreenPlan.Web.Models;

namespace GreenPlan.Web.Presentation;

public static class StageStates
{
    public const string Done = "done";
    public const string Current = "current";
    public const string Failed = "failed";
    public const string Pending = "pending";
}

public sealed record StageProgress(string Key, string Title, string State, double? Seconds)
{
    public string TimeText => Seconds is { } seconds ? DurationText.For(seconds) : "—";
}

public sealed record JobTimeline(IReadOnlyList<StageProgress> Stages, double? ElapsedSeconds)
{
    public string ElapsedText => ElapsedSeconds is { } seconds ? DurationText.For(seconds) : "—";

    public static JobTimeline From(JobDto job, DateTimeOffset now)
    {
        var finished = FinishedTimings(job);
        var stages = StageNames.Keys
            .Select(key => Progress(job, key, finished, now))
            .ToList();
        return new JobTimeline(stages, Elapsed(job, now));
    }

    private static StageProgress Progress(
        JobDto job,
        string key,
        IReadOnlyDictionary<string, double> finished,
        DateTimeOffset now)
    {
        var title = StageNames.For(key);
        if (finished.TryGetValue(key, out var seconds))
        {
            return new StageProgress(key, title, StageStates.Done, seconds);
        }

        if (key != job.Stage)
        {
            return new StageProgress(key, title, StageStates.Pending, null);
        }

        return job.Status switch
        {
            JobStatuses.Running => new StageProgress(key, title, StageStates.Current, Between(job.StageStartedAt, now)),
            JobStatuses.Failed => new StageProgress(key, title, StageStates.Failed, Between(job.StageStartedAt, Parse(job.FinishedAt))),
            _ => new StageProgress(key, title, StageStates.Pending, null),
        };
    }

    private static IReadOnlyDictionary<string, double> FinishedTimings(JobDto job)
    {
        if (job.StageTimings is { Count: > 0 } timings)
        {
            return timings;
        }

        return new JobSummaryView(job.Summary).Timings().ToDictionary(timing => timing.Stage, timing => timing.Seconds);
    }

    private static double? Elapsed(JobDto job, DateTimeOffset now)
    {
        var end = JobStatusText.IsFinished(job.Status) ? Parse(job.FinishedAt) : now;
        return Between(job.StartedAt, end);
    }

    private static double? Between(string? start, DateTimeOffset? end)
    {
        var begin = Parse(start);
        if (begin is null || end is null)
        {
            return null;
        }

        return Math.Max(0.0, (end.Value - begin.Value).TotalSeconds);
    }

    private static DateTimeOffset? Parse(string? timestamp) =>
        DateTimeOffset.TryParse(timestamp, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out var value)
            ? value
            : null;
}

public static class DurationText
{
    private static readonly CultureInfo Russian = CultureInfo.GetCultureInfo("ru-RU");

    public static string For(double seconds)
    {
        if (seconds < 60)
        {
            return $"{seconds.ToString("0.#", Russian)} с";
        }

        var whole = TimeSpan.FromSeconds(Math.Round(seconds));
        return whole.TotalHours >= 1
            ? $"{(int)whole.TotalHours} ч {whole.Minutes:00} мин"
            : $"{whole.Minutes} мин {whole.Seconds:00} с";
    }
}
