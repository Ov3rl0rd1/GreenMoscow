using GreenPlan.Web.Services;

namespace GreenPlan.Web.Endpoints;

public static class ArtifactEndpoints
{
    public const string Route = "/jobs/{jobId}/artifacts/{name}";

    public static IEndpointRouteBuilder MapArtifactEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapGet(Route, DownloadAsync);
        return endpoints;
    }

    public static string UrlFor(string jobId, string name) =>
        $"/jobs/{Uri.EscapeDataString(jobId)}/artifacts/{Uri.EscapeDataString(name)}";

    private static async Task<IResult> DownloadAsync(
        string jobId,
        string name,
        IEngineClient engine,
        CancellationToken cancellationToken)
    {
        try
        {
            var artifact = await engine.GetArtifactAsync(jobId, name, cancellationToken);
            return artifact is null ? Results.NotFound() : Results.File(artifact.Content, artifact.ContentType, name);
        }
        catch (EngineRequestException error)
        {
            return Results.Problem(error.Message, statusCode: StatusCodes.Status502BadGateway);
        }
    }
}
