using System.Net;
using System.Text;
using GreenPlan.Web.Models;
using GreenPlan.Web.Presentation;
using GreenPlan.Web.Services;
using GreenPlan.Web.Tests.Support;

namespace GreenPlan.Web.Tests;

public sealed class EngineClientTests
{
    private static readonly Uri EngineAddress = new("http://engine/");

    private static EngineClient ClientFor(FakeHttpMessageHandler handler) =>
        new(new HttpClient(handler) { BaseAddress = EngineAddress });

    private static JobSubmission Submission(string? mainFile = null, string? config = null) =>
        new(new MemoryStream(Encoding.UTF8.GetBytes("0\nSECTION")), "street.dxf", "Улица", mainFile, config);

    [Fact]
    public async Task CreateJobSendsEveryFormFieldAndReadsJob()
    {
        var handler = FakeHttpMessageHandler.Returning(HttpStatusCode.Accepted, TestJobs.SucceededJson);
        var job = await ClientFor(handler).CreateJobAsync(
            Submission("объект/главный.dwg", "placement:\n  cell_size_m: 1\n"),
            CancellationToken.None);
        var request = handler.Requests.Single();

        Assert.Equal(HttpMethod.Post, request.Method);
        Assert.Equal($"/{EngineClient.JobsPath}", request.Path);
        Assert.Contains("filename=street.dxf", request.Body);
        Assert.Contains("name=title", request.Body);
        Assert.Contains("Улица", request.Body);
        Assert.Contains("объект/главный.dwg", request.Body);
        Assert.Contains("cell_size_m", request.Body);
        Assert.Equal(TestJobs.SucceededId, job.JobId);
    }

    [Fact]
    public async Task JobSummaryKeepsSnakeCaseNumbersAndFlags()
    {
        var handler = FakeHttpMessageHandler.Returning(HttpStatusCode.OK, TestJobs.SucceededJson);
        var job = await ClientFor(handler).GetJobAsync(TestJobs.SucceededId, CancellationToken.None);
        var summary = new JobSummaryView(job!.Summary);

        Assert.Equal(75, summary.Integer("trees"));
        Assert.True(summary.Flag("verification_valid"));
        Assert.Contains(summary.Timings(), timing => timing.Stage == "verify");
    }

    [Fact]
    public async Task MissingJobBecomesNull()
    {
        var handler = FakeHttpMessageHandler.Returning(HttpStatusCode.NotFound, """{"detail":"job not found"}""");
        Assert.Null(await ClientFor(handler).GetJobAsync("unknown", CancellationToken.None));
    }

    [Fact]
    public async Task RejectedUploadCarriesEngineDetail()
    {
        var handler = FakeHttpMessageHandler.Returning(
            HttpStatusCode.BadRequest,
            """{"detail":"main_file is required: the upload contains 2 drawings"}""");

        var error = await Assert.ThrowsAsync<EngineRequestException>(
            () => ClientFor(handler).CreateJobAsync(Submission(), CancellationToken.None));

        Assert.Contains("main_file is required", error.Message);
        Assert.Contains("400", error.Message);
    }

    [Fact]
    public async Task UnavailableEngineBecomesDomainError()
    {
        var handler = FakeHttpMessageHandler.Throwing(new HttpRequestException("connection refused"));

        var error = await Assert.ThrowsAsync<EngineRequestException>(
            () => ClientFor(handler).ListJobsAsync(CancellationToken.None));

        Assert.Contains("недоступен", error.Message);
    }

    [Fact]
    public async Task UnavailableEngineMakesHealthNull()
    {
        var handler = FakeHttpMessageHandler.Throwing(new HttpRequestException("connection refused"));
        Assert.Null(await ClientFor(handler).GetHealthAsync(CancellationToken.None));
    }

    [Fact]
    public async Task ArtifactKeepsBytesContentTypeAndEscapedName()
    {
        var handler = new FakeHttpMessageHandler(_ => new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new ByteArrayContent([1, 2, 3])
            {
                Headers = { ContentType = new System.Net.Http.Headers.MediaTypeHeaderValue("image/png") },
            },
        });

        var artifact = await ClientFor(handler).GetArtifactAsync(
            TestJobs.SucceededId,
            "planting report.md",
            CancellationToken.None);

        Assert.Equal(new byte[] { 1, 2, 3 }, artifact!.Content);
        Assert.Equal("image/png", artifact.ContentType);
        Assert.Contains("planting%20report.md", handler.Requests.Single().Path);
    }

    [Fact]
    public async Task MissingArtifactBecomesNull()
    {
        var handler = FakeHttpMessageHandler.Returning(HttpStatusCode.NotFound, "{}");
        Assert.Null(await ClientFor(handler).GetArtifactAsync("job", "missing.png", CancellationToken.None));
    }

    [Fact]
    public async Task HealthMapsSnakeCaseFlag()
    {
        var handler = FakeHttpMessageHandler.Returning(
            HttpStatusCode.OK,
            """{"status":"ok","version":"0.1.0","dwg2dxf_available":true}""");

        var health = await ClientFor(handler).GetHealthAsync(CancellationToken.None);

        Assert.Equal("ok", health!.Status);
        Assert.Equal("0.1.0", health.Version);
        Assert.True(health.Dwg2dxfAvailable);
    }
}
