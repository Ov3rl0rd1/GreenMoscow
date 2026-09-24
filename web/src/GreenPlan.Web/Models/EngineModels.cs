using System.Text.Json;

namespace GreenPlan.Web.Models;

public sealed record JobDto(
    string JobId,
    string Status,
    string Title,
    string CreatedAt,
    string UpdatedAt,
    string UploadName,
    string MainFile,
    string? Error,
    IReadOnlyList<string> Artifacts,
    IReadOnlyDictionary<string, JsonElement> Summary,
    IReadOnlyList<string>? OverlayFiles = null,
    string? Stage = null,
    string? Guidance = null);

public sealed record HealthDto(string Status, string Version, bool Dwg2dxfAvailable, bool ModelAvailable = false);

public sealed record TerritoryDto(string Id, string NameRu, string CompositionRu);

public sealed record UploadedDrawing(Stream Content, string FileName);

public sealed record JobSubmission(
    IReadOnlyList<UploadedDrawing> Drawings,
    string Title,
    string? MainFile,
    string? ConfigYaml,
    string? Territory = null,
    string? Guidance = null);

public sealed record EngineArtifact(byte[] Content, string ContentType);

public static class GuidanceChoices
{
    public const string Model = "model";
    public const string Rules = "rules";
}

public static class JobStatuses
{
    public const string Queued = "queued";
    public const string Running = "running";
    public const string Succeeded = "succeeded";
    public const string Failed = "failed";
}
