using System.Text.Json;
using GreenPlan.Web.Models;

namespace GreenPlan.Web.Tests.Support;

public static class TestJobs
{
    public const string SucceededId = "1111111111111111111111111111aaaa";
    public const string RunningId = "2222222222222222222222222222bbbb";

    public const string SucceededJson = """
        {
          "job_id": "1111111111111111111111111111aaaa",
          "status": "succeeded",
          "title": "Улица Багрицкого",
          "created_at": "2026-09-15T10:00:00+00:00",
          "updated_at": "2026-09-15T10:03:00+00:00",
          "upload_name": "bagritskogo.zip",
          "main_file": "Исходные данные/ГП и ПБ.dwg",
          "error": null,
          "artifacts": ["planting_report.json", "preview.png", "street_greenplan.dxf"],
          "summary": {
            "trees": 75,
            "shrubs": 1098,
            "conditional": 179,
            "rejected": 215,
            "verification_valid": true,
            "violations": 0,
            "integrity_is_intact": true,
            "timings_s": {"read_drawings": 88.4, "verify": 27.2}
          }
        }
        """;

    public static JobDto Succeeded() => Parse(SucceededJson);

    public static JobDto Running() =>
        Succeeded() with
        {
            JobId = RunningId,
            Status = JobStatuses.Running,
            Title = "Улица в работе",
            Artifacts = [],
            Summary = new Dictionary<string, JsonElement>(),
        };

    public static JobDto Parse(string json) =>
        JsonSerializer.Deserialize<JobDto>(json, GreenPlan.Web.Services.EngineClient.JsonOptions)
        ?? throw new InvalidOperationException("job json is empty");
}
