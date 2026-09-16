using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.RegularExpressions;
using GreenPlan.Web.Services;
using GreenPlan.Web.Tests.Support;

namespace GreenPlan.Web.Tests;

public sealed class PagesTests
{
    private static readonly Regex TokenPattern = new("name=\"__RequestVerificationToken\"[^>]*value=\"([^\"]+)\"");
    private static readonly byte[] DrawingBytes = Encoding.UTF8.GetBytes("0\nSECTION");

    [Fact]
    public async Task IndexShowsUploadFormAndRecentJobs()
    {
        using var factory = new GreenPlanWebFactory();
        using var client = factory.CreateClient();

        var html = await client.GetStringAsync("/");

        Assert.Contains("multipart/form-data", html);
        Assert.Contains("Улица Багрицкого", html);
        Assert.Contains("готово", html);
    }

    [Fact]
    public async Task IndexWarnsWhenEngineIsUnavailable()
    {
        using var factory = new GreenPlanWebFactory();
        factory.Engine.Health = null;
        using var client = factory.CreateClient();

        Assert.Contains("недоступен", await client.GetStringAsync("/"));
    }

    [Fact]
    public async Task UploadRedirectsToJobAndPassesEveryField()
    {
        using var factory = new GreenPlanWebFactory();
        using var client = factory.CreateNonRedirectingClient();
        var token = await AntiforgeryTokenAsync(client);

        using var content = UploadContent(token, "Улица", "объект/главный.dwg", DrawingBytes);
        using var response = await client.PostAsync("/", content);
        var submission = factory.Engine.LastSubmission;

        Assert.Equal(HttpStatusCode.Redirect, response.StatusCode);
        Assert.Equal($"/Jobs/Details/{TestJobs.SucceededId}", response.Headers.Location?.OriginalString);
        Assert.Equal("street.dxf", submission?.FileName);
        Assert.Equal("Улица", submission?.Title);
        Assert.Equal("объект/главный.dwg", submission?.MainFile);
        Assert.Equal("0\nSECTION", submission?.Content);
    }

    [Fact]
    public async Task UploadWithoutDrawingShowsValidationMessage()
    {
        using var factory = new GreenPlanWebFactory();
        using var client = factory.CreateNonRedirectingClient();
        var token = await AntiforgeryTokenAsync(client);

        using var content = UploadContent(token, "Улица");
        using var response = await client.PostAsync("/", content);

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Contains("Выберите чертёж", await response.Content.ReadAsStringAsync());
        Assert.Null(factory.Engine.LastSubmission);
    }

    [Fact]
    public async Task EngineErrorIsShownOnTheForm()
    {
        using var factory = new GreenPlanWebFactory();
        factory.Engine.CreateFailure = new EngineRequestException("Сервис расчёта вернул 400: main_file is required");
        using var client = factory.CreateNonRedirectingClient();
        var token = await AntiforgeryTokenAsync(client);

        using var content = UploadContent(token, "Улица", drawing: DrawingBytes);
        using var response = await client.PostAsync("/", content);

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Contains("main_file is required", await response.Content.ReadAsStringAsync());
    }

    [Fact]
    public async Task JobPageShowsSummaryPreviewAndArtifacts()
    {
        using var factory = new GreenPlanWebFactory();
        using var client = factory.CreateClient();

        var html = await client.GetStringAsync($"/Jobs/Details/{TestJobs.SucceededId}");

        Assert.Contains("75", html);
        Assert.Contains("1098", html);
        Assert.Contains("пройдена", html);
        Assert.Contains("Независимая проверка", html);
        Assert.Contains($"/jobs/{TestJobs.SucceededId}/artifacts/preview.png", html);
        Assert.DoesNotContain("http-equiv=\"refresh\"", html);
    }

    [Fact]
    public async Task RunningJobPageRefreshesItself()
    {
        using var factory = new GreenPlanWebFactory();
        factory.Engine.Jobs.Add(TestJobs.Running());
        using var client = factory.CreateClient();

        var html = await client.GetStringAsync($"/Jobs/Details/{TestJobs.RunningId}");

        Assert.Contains("http-equiv=\"refresh\"", html);
        Assert.Contains("выполняется", html);
    }

    [Fact]
    public async Task UnknownJobPageIsNotFound()
    {
        using var factory = new GreenPlanWebFactory();
        using var client = factory.CreateClient();

        using var response = await client.GetAsync("/Jobs/Details/unknown");

        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
    }

    [Fact]
    public async Task ArtifactProxyReturnsFileAndMissingArtifactIsNotFound()
    {
        using var factory = new GreenPlanWebFactory();
        using var client = factory.CreateClient();

        using var preview = await client.GetAsync($"/jobs/{TestJobs.SucceededId}/artifacts/preview.png");
        using var missing = await client.GetAsync($"/jobs/{TestJobs.SucceededId}/artifacts/missing.png");

        Assert.Equal(HttpStatusCode.OK, preview.StatusCode);
        Assert.Equal("image/png", preview.Content.Headers.ContentType?.MediaType);
        Assert.Equal(new byte[] { 1, 2, 3 }, await preview.Content.ReadAsByteArrayAsync());
        Assert.Equal(HttpStatusCode.NotFound, missing.StatusCode);
    }

    [Fact]
    public async Task HealthEndpointIsAvailable()
    {
        using var factory = new GreenPlanWebFactory();
        using var client = factory.CreateClient();

        using var response = await client.GetAsync("/healthz");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    private static async Task<string> AntiforgeryTokenAsync(HttpClient client)
    {
        var match = TokenPattern.Match(await client.GetStringAsync("/"));
        Assert.True(match.Success, "форма не содержит антифорджери-токен");
        return match.Groups[1].Value;
    }

    private static MultipartFormDataContent UploadContent(
        string token,
        string title,
        string? mainFile = null,
        byte[]? drawing = null)
    {
        var content = new MultipartFormDataContent
        {
            { new StringContent(token), "__RequestVerificationToken" },
            { new StringContent(title, Encoding.UTF8), "Form.Title" },
        };

        if (mainFile is not null)
        {
            content.Add(new StringContent(mainFile, Encoding.UTF8), "Form.MainFile");
        }

        if (drawing is not null)
        {
            var file = new ByteArrayContent(drawing);
            file.Headers.ContentType = new MediaTypeHeaderValue("application/octet-stream");
            content.Add(file, "Form.Drawing", "street.dxf");
        }

        return content;
    }
}
