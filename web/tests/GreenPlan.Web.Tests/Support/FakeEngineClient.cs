using System.Text;
using GreenPlan.Web.Models;
using GreenPlan.Web.Services;

namespace GreenPlan.Web.Tests.Support;

public sealed record SubmittedJob(string FileName, string Title, string? MainFile, string? ConfigYaml, string Content);

public sealed class FakeEngineClient : IEngineClient
{
    public List<JobDto> Jobs { get; } = [TestJobs.Succeeded()];

    public Dictionary<string, EngineArtifact> Artifacts { get; } =
        new() { ["preview.png"] = new EngineArtifact([1, 2, 3], "image/png") };

    public HealthDto? Health { get; set; } = new("ok", "0.1.0", true);

    public Exception? CreateFailure { get; set; }

    public SubmittedJob? LastSubmission { get; private set; }

    public Task<JobDto> CreateJobAsync(JobSubmission submission, CancellationToken cancellationToken)
    {
        using var reader = new StreamReader(submission.Drawing, Encoding.UTF8, leaveOpen: true);
        LastSubmission = new SubmittedJob(
            submission.FileName,
            submission.Title,
            submission.MainFile,
            submission.ConfigYaml,
            reader.ReadToEnd());
        if (CreateFailure is not null)
        {
            return Task.FromException<JobDto>(CreateFailure);
        }

        return Task.FromResult(Jobs[0]);
    }

    public Task<JobDto?> GetJobAsync(string jobId, CancellationToken cancellationToken) =>
        Task.FromResult(Jobs.FirstOrDefault(job => job.JobId == jobId));

    public Task<IReadOnlyList<JobDto>> ListJobsAsync(CancellationToken cancellationToken) =>
        Task.FromResult<IReadOnlyList<JobDto>>(Jobs);

    public Task<EngineArtifact?> GetArtifactAsync(string jobId, string name, CancellationToken cancellationToken) =>
        Task.FromResult(Artifacts.GetValueOrDefault(name));

    public Task<HealthDto?> GetHealthAsync(CancellationToken cancellationToken) => Task.FromResult(Health);
}
