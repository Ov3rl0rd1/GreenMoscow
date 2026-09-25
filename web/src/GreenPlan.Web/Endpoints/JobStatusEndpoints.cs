using GreenPlan.Web.Presentation;
using GreenPlan.Web.Services;

namespace GreenPlan.Web.Endpoints;

public static class JobStatusEndpoints
{
    public const string Route = "/jobs/{jobId}/status";

    public static IEndpointRouteBuilder MapJobStatusEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapGet(Route, StatusAsync);
        return endpoints;
    }

    public static string UrlFor(string jobId) => $"/jobs/{Uri.EscapeDataString(jobId)}/status";

    private static async Task<IResult> StatusAsync(
        string jobId,
        IEngineClient engine,
        TimeProvider clock,
        HttpResponse response,
        CancellationToken cancellationToken)
    {
        response.Headers.CacheControl = "no-store";
        try
        {
            var job = await engine.GetJobAsync(jobId, cancellationToken);
            return job is null ? Results.NotFound() : Results.Ok(JobStatusView.From(job, clock.GetUtcNow()));
        }
        catch (EngineRequestException error)
        {
            return Results.Problem(error.Message, statusCode: StatusCodes.Status502BadGateway);
        }
    }
}
