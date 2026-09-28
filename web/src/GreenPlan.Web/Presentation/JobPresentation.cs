using System.Globalization;
using System.Text.Json;
using GreenPlan.Web.Models;

namespace GreenPlan.Web.Presentation;

public static class MomentText
{
    public static string For(string? moment) =>
        DateTimeOffset.TryParse(moment, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out var parsed)
            ? parsed.ToUniversalTime().ToString("dd.MM.yyyy HH:mm", CultureInfo.InvariantCulture) + " UTC"
            : moment ?? string.Empty;
}

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

    public static IEnumerable<string> Keys => Ordered.Select(item => item.Key);

    public static string For(string stage) => Names.TryGetValue(stage, out var name) ? name : stage;

    public static int NumberOf(string stage) => Ordered.Select(item => item.Key).ToList().IndexOf(stage) + 1;
}

public static class ElementNames
{
    private static readonly IReadOnlyDictionary<string, string> Names = new Dictionary<string, string>
    {
        ["row"] = "ряды",
        ["group"] = "группы деревьев",
        ["solitary"] = "солитёры",
        ["hedge"] = "живые изгороди",
        ["shrub_group"] = "куртины кустарника",
    };

    public static string For(string kind) => Names.TryGetValue(kind, out var name) ? name : kind;
}

public static class GuidanceText
{
    public static string For(string? guidance) => guidance switch
    {
        GuidanceChoices.Model => "модель, обученная на проектных решениях датасета; нормы проверены движком",
        GuidanceChoices.Rules => "правила движка: отступы, края газона, норматив плотности",
        _ => "—",
    };
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

public sealed record JobStatusView(
    string Status,
    string StatusText,
    string ProgressText,
    bool Finished,
    IReadOnlyList<StageProgressView> Stages,
    double? ElapsedSeconds,
    string ElapsedText)
{
    public static JobStatusView From(JobDto job, DateTimeOffset now)
    {
        var timeline = JobTimeline.From(job, now);
        return new JobStatusView(
            job.Status,
            JobStatusText.For(job.Status),
            JobProgressText.For(job),
            JobStatusText.IsFinished(job.Status),
            timeline.Stages.Select(StageProgressView.From).ToList(),
            timeline.ElapsedSeconds,
            timeline.ElapsedText);
    }
}

public sealed record StageProgressView(string Key, string State, double? Seconds, string TimeText)
{
    public static StageProgressView From(StageProgress stage) => new(stage.Key, stage.State, stage.Seconds, stage.TimeText);
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

    public string? Text(string key) =>
        summary.TryGetValue(key, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;

    public bool? Flag(string key) =>
        summary.TryGetValue(key, out var value) && value.ValueKind is JsonValueKind.True or JsonValueKind.False
            ? value.GetBoolean()
            : null;

    public IReadOnlyList<string> Journal() =>
        summary.TryGetValue("journal", out var value) && value.ValueKind == JsonValueKind.Array
            ? value.EnumerateArray().Select(item => item.GetString() ?? string.Empty).Where(text => text.Length > 0).ToList()
            : [];

    public IReadOnlyList<string> Warnings() =>
        summary.TryGetValue("warnings", out var value) && value.ValueKind == JsonValueKind.Array
            ? value.EnumerateArray().Select(item => item.GetString() ?? string.Empty).Where(text => text.Length > 0).ToList()
            : [];

    public string? CompositionText()
    {
        if (!Benefits().TryGetProperty("elements", out var elements) || elements.ValueKind != JsonValueKind.Object)
        {
            return null;
        }

        var parts = elements.EnumerateObject()
            .Where(item => item.Value.ValueKind == JsonValueKind.Number)
            .Select(item => $"{ElementNames.For(item.Name)} — {item.Value.GetInt32()}")
            .ToList();
        if (Benefits().TryGetProperty("rows_with_hedge", out var hedged) && hedged.ValueKind == JsonValueKind.Number && hedged.GetInt32() > 0)
        {
            parts.Add($"аллеи с живой изгородью — {hedged.GetInt32()}");
        }

        return parts.Count > 0 ? string.Join(", ", parts) : null;
    }

    public string? BenefitText()
    {
        var front = Percent("street_front_share");
        var shade = Percent("sidewalk_shade_share");
        var open = Percent("open_lawn_share");
        if (front is null && shade is null && open is null)
        {
            return null;
        }

        return $"проезжая часть отделена посадками на {front ?? "—"} фронта; тротуары под кронами — {shade ?? "—"}; открытый газон — {open ?? "—"}";
    }

    private string? Percent(string key) =>
        Benefits().TryGetProperty(key, out var value) && value.ValueKind == JsonValueKind.Number
            ? $"{(value.GetDouble() * 100).ToString("0", CultureInfo.GetCultureInfo("ru-RU"))} %"
            : null;

    private JsonElement Benefits() =>
        summary.TryGetValue("benefits", out var value) && value.ValueKind == JsonValueKind.Object ? value : default;

    public IReadOnlyList<StageTiming> Timings() =>
        summary.TryGetValue(TimingsKey, out var value) && value.ValueKind == JsonValueKind.Object
            ? value.EnumerateObject().Select(stage => new StageTiming(stage.Name, stage.Value.GetDouble())).ToList()
            : [];
}
