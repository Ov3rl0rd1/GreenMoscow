using GreenPlan.Web.Models;

namespace GreenPlan.Web.Services;

public interface IEngineClient
{
    Task<JobDto> CreateJobAsync(JobSubmission submission, CancellationToken cancellationToken);

    Task<JobDto?> GetJobAsync(string jobId, CancellationToken cancellationToken);

    Task<IReadOnlyList<JobDto>> ListJobsAsync(CancellationToken cancellationToken);

    Task<EngineArtifact?> GetArtifactAsync(string jobId, string name, CancellationToken cancellationToken);

    Task<HealthDto?> GetHealthAsync(CancellationToken cancellationToken);
}

public sealed class EngineRequestException(string message, Exception? innerException = null)
    : Exception(message, innerException);
