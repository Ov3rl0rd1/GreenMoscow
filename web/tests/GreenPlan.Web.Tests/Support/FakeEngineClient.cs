using System.Text;
using GreenPlan.Web.Models;
using GreenPlan.Web.Services;

namespace GreenPlan.Web.Tests.Support;

public sealed record SubmittedJob(
    IReadOnlyList<string> FileNames,
    string Title,
    string? Territory,
    string? MainFile,
    string? ConfigYaml,
    IReadOnlyList<string> Contents,
    string? Guidance = null,
    bool ExceedDensity = false,
    string? SettingsJson = null)
{
    public string FileName => FileNames[0];

    public string Content => Contents[0];
}

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
        LastSubmission = new SubmittedJob(
            submission.Drawings.Select(drawing => drawing.FileName).ToList(),
            submission.Title,
            submission.Territory,
            submission.MainFile,
            submission.ConfigYaml,
            submission.Drawings.Select(drawing => ReadAll(drawing.Content)).ToList(),
            submission.Guidance,
            submission.ExceedDensity,
            submission.SettingsJson);
        if (CreateFailure is not null)
        {
            return Task.FromException<JobDto>(CreateFailure);
        }

        return Task.FromResult(Jobs[0]);
    }

    private static string ReadAll(Stream stream)
    {
        using var reader = new StreamReader(stream, Encoding.UTF8, leaveOpen: true);
        return reader.ReadToEnd();
    }

    public Task<JobDto?> GetJobAsync(string jobId, CancellationToken cancellationToken) =>
        Task.FromResult(Jobs.FirstOrDefault(job => job.JobId == jobId));

    public Task<IReadOnlyList<JobDto>> ListJobsAsync(CancellationToken cancellationToken) =>
        Task.FromResult<IReadOnlyList<JobDto>>(Jobs);

    public Task<EngineArtifact?> GetArtifactAsync(string jobId, string name, CancellationToken cancellationToken) =>
        Task.FromResult(Artifacts.GetValueOrDefault(name));

    public Task<HealthDto?> GetHealthAsync(CancellationToken cancellationToken) => Task.FromResult(Health);

    public Task<IReadOnlyList<TerritoryDto>> ListTerritoriesAsync(CancellationToken cancellationToken) =>
        Task.FromResult<IReadOnlyList<TerritoryDto>>(
            [new TerritoryDto("residential_yard", "дворовая территория", "группы без аллей")]);
}
