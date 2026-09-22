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
    private static readonly IReadOnlyDictionary<string, string> Names = new Dictionary<string, string>
    {
        ["read_drawings"] = "Чтение чертежей и внешних ссылок",
        ["recognize_site"] = "Распознавание участка",
        ["place_plants"] = "Размещение посадок",
        ["select_species"] = "Подбор пород",
        ["explain"] = "Объяснения и отчёты",
        ["export_dxf"] = "Экспорт DXF и превью",
        ["verify"] = "Независимая проверка",
    };

    public static string For(string stage) => Names.TryGetValue(stage, out var name) ? name : stage;
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
