using System.Globalization;
using System.Text.Json;
using GreenPlan.Web.Models;

namespace GreenPlan.Web.Presentation;

public static class JobStatusText
{
    private static readonly IReadOnlyDictionary<string, string> Texts = new Dictionary<string, string>
    {
        [JobStatuses.Queued] = "в очереди",
        [JobStatuses.Running] = "выполняется",
        [JobStatuses.Succeeded] = "готово",
        [JobStatuses.Failed] = "ошибка",
    };

    public static string For(string status) => Texts.TryGetValue(status, out var text) ? text : status;

    public static bool IsFinished(string status) => status is JobStatuses.Succeeded or JobStatuses.Failed;
}

public static class StageNames
{
    private static readonly IReadOnlyList<KeyValuePair<string, string>> Ordered =
    [
        new("read_drawings", "Чтение чертежей и внешних ссылок"),
        new("recognize_site", "Распознавание участка"),
        new("place_plants", "Размещение посадок"),
        new("select_species", "Подбор пород"),
        new("explain", "Объяснения и отчёты"),
        new("export_dxf", "Экспорт DXF и превью"),
        new("verify", "Независимая проверка"),
    ];

    private static readonly IReadOnlyDictionary<string, string> Names = Ordered.ToDictionary();

    public static int Count => Ordered.Count;

    public static string For(string stage) => Names.TryGetValue(stage, out var name) ? name : stage;

    public static int NumberOf(string stage) => Ordered.Select(item => item.Key).ToList().IndexOf(stage) + 1;
}

public static class JobProgressText
{
    public static string For(JobDto job) => job.Status switch
    {
        JobStatuses.Queued => "Ждёт своей очереди: расчёты выполняются по одному.",
        JobStatuses.Running when !string.IsNullOrEmpty(job.Stage) && StageNames.NumberOf(job.Stage) > 0 =>
            $"Этап {StageNames.NumberOf(job.Stage)} из {StageNames.Count}: {StageNames.For(job.Stage)}.",
        JobStatuses.Running => "Запуск расчёта.",
        _ => string.Empty,
    };
}

public sealed record JobStatusView(string Status, string StatusText, string ProgressText, bool Finished)
{
    public static JobStatusView From(JobDto job) =>
        new(job.Status, JobStatusText.For(job.Status), JobProgressText.For(job), JobStatusText.IsFinished(job.Status));
}

public sealed record StageTiming(string Stage, double Seconds)
{
    public string SecondsText => Seconds.ToString("0.#", CultureInfo.GetCultureInfo("ru-RU"));
}

public sealed class JobSummaryView(IReadOnlyDictionary<string, JsonElement> summary)
{
    public const string TimingsKey = "timings_s";

    public int? Integer(string key) =>
        summary.TryGetValue(key, out var value) && value.ValueKind == JsonValueKind.Number ? value.GetInt32() : null;

    public bool? Flag(string key) =>
        summary.TryGetValue(key, out var value) && value.ValueKind is JsonValueKind.True or JsonValueKind.False
            ? value.GetBoolean()
            : null;

    public IReadOnlyList<string> Warnings() =>
        summary.TryGetValue("warnings", out var value) && value.ValueKind == JsonValueKind.Array
            ? value.EnumerateArray().Select(item => item.GetString() ?? string.Empty).Where(text => text.Length > 0).ToList()
            : [];

    public IReadOnlyList<StageTiming> Timings() =>
        summary.TryGetValue(TimingsKey, out var value) && value.ValueKind == JsonValueKind.Object
            ? value.EnumerateObject().Select(stage => new StageTiming(stage.Name, stage.Value.GetDouble())).ToList()
            : [];
}
