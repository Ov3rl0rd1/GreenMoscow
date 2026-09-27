using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
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
    public async Task IndexOffersTerritoryCategoriesFromTheEngine()
    {
        using var factory = new GreenPlanWebFactory();
        using var client = factory.CreateClient();

        var html = await client.GetStringAsync("/");

        Assert.Contains("дворовая территория", html);
        Assert.Contains("Form.Territory", html);
    }

    [Fact]
    public async Task ChosenTerritoryReachesTheEngine()
    {
        using var factory = new GreenPlanWebFactory();
        using var client = factory.CreateNonRedirectingClient();
        var token = await AntiforgeryTokenAsync(client);

        using var content = UploadContent(token, "Двор", drawing: DrawingBytes, territory: "residential_yard");
        using var response = await client.PostAsync("/", content);

        Assert.Equal(HttpStatusCode.Redirect, response.StatusCode);
        Assert.Equal("residential_yard", factory.Engine.LastSubmission?.Territory);
    }

    [Fact]
    public async Task ModelChoiceIsOfferedOnlyWhenTheEngineHasAModel()
    {
        using var withModel = new GreenPlanWebFactory();
        withModel.Engine.Health = new("ok", "0.1.0", true, ModelAvailable: true);
        using var withoutModel = new GreenPlanWebFactory();

        var offered = await withModel.CreateClient().GetStringAsync("/");
        var hidden = await withoutModel.CreateClient().GetStringAsync("/");

        Assert.Contains("type=\"checkbox\"", offered);
        Assert.DoesNotContain("type=\"checkbox\"", hidden);
    }

    [Fact]
    public async Task UploadWithTheModelSwitchedOffAsksForRules()
    {
        using var factory = new GreenPlanWebFactory();
        using var client = factory.CreateNonRedirectingClient();
        var token = await AntiforgeryTokenAsync(client);

        using var content = UploadContent(token, "Улица", drawing: DrawingBytes);
        content.Add(new StringContent("false", Encoding.UTF8), "Form.UseModel");
        using var response = await client.PostAsync("/", content);

        Assert.Equal(HttpStatusCode.Redirect, response.StatusCode);
        Assert.Equal("rules", factory.Engine.LastSubmission?.Guidance);
    }

    [Fact]
    public async Task DensityExcessIsOfferedWithAnExplanationAndSentWhenChosen()
    {
        using var factory = new GreenPlanWebFactory();
        factory.Engine.Health = new("ok", "0.1.0", true, ModelAvailable: true);
        using var client = factory.CreateNonRedirectingClient();

        var page = await client.GetStringAsync("/");
        var token = await AntiforgeryTokenAsync(client);
        using var content = UploadContent(token, "Улица", drawing: DrawingBytes);
        content.Add(new StringContent("true", Encoding.UTF8), "Form.ExceedDensity");
        using var response = await client.PostAsync("/", content);

        Assert.Contains("Разрешить превышать рекомендательный норматив плотности", page);
        Assert.Contains("Последствия:", page);
        Assert.True(factory.Engine.LastSubmission?.ExceedDensity);
    }

    [Fact]
    public async Task DensityExcessIsNotSentWithoutTheModel()
    {
        using var factory = new GreenPlanWebFactory();
        using var client = factory.CreateNonRedirectingClient();
        var token = await AntiforgeryTokenAsync(client);

        using var content = UploadContent(token, "Улица", drawing: DrawingBytes);
        content.Add(new StringContent("false", Encoding.UTF8), "Form.UseModel");
        content.Add(new StringContent("true", Encoding.UTF8), "Form.ExceedDensity");
        using var response = await client.PostAsync("/", content);

        Assert.False(factory.Engine.LastSubmission?.ExceedDensity);
    }

    [Fact]
    public async Task UploadAsksForTheModelByDefault()
    {
        using var factory = new GreenPlanWebFactory();
        using var client = factory.CreateNonRedirectingClient();
        var token = await AntiforgeryTokenAsync(client);

        using var content = UploadContent(token, "Улица", drawing: DrawingBytes);
        using var response = await client.PostAsync("/", content);

        Assert.Equal("model", factory.Engine.LastSubmission?.Guidance);
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
    public async Task SeveralDrawingsReachTheEngineTogether()
    {
        using var factory = new GreenPlanWebFactory();
        using var client = factory.CreateNonRedirectingClient();
        var token = await AntiforgeryTokenAsync(client);

        using var content = UploadContent(token, "Улица", drawing: DrawingBytes);
        var baseDrawing = new ByteArrayContent(Encoding.UTF8.GetBytes("0\nEOF"));
        baseDrawing.Headers.ContentType = new MediaTypeHeaderValue("application/octet-stream");
        content.Add(baseDrawing, "Form.Drawing", "base.dxf");
        using var response = await client.PostAsync("/", content);
        var submission = factory.Engine.LastSubmission;

        Assert.Equal(HttpStatusCode.Redirect, response.StatusCode);
        Assert.Equal(["street.dxf", "base.dxf"], submission?.FileNames);
        Assert.Equal(["0\nSECTION", "0\nEOF"], submission?.Contents);
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
        Assert.Contains("модель, обученная на проектных решениях датасета", html);
        Assert.Contains("ряды — 4, группы деревьев — 7, живые изгороди — 3, аллеи с живой изгородью — 2", html);
        Assert.Contains("Закрыто проблем: 1", html);
        Assert.Contains("пустой участок газона (420 м²): группа деревьев — 5 шт.", html);
        Assert.Contains("проезжая часть отделена посадками на 62 % фронта", html);
        Assert.Contains($"/jobs/{TestJobs.SucceededId}/artifacts/preview.png", html);
        Assert.DoesNotContain("http-equiv=\"refresh\"", html);
    }

    [Fact]
    public async Task JobPageShowsSiteWarnings()
    {
        using var factory = new GreenPlanWebFactory();
        using var client = factory.CreateClient();

        var html = await client.GetStringAsync($"/Jobs/Details/{TestJobs.SucceededId}");

        Assert.Contains("На что обратить внимание", html);
        Assert.Contains("подземные коммуникации во входных чертежах не найдены", html);
    }

    [Fact]
    public async Task RunningJobPageFollowsProgressWithoutReloading()
    {
        using var factory = new GreenPlanWebFactory();
        factory.Engine.Jobs.Add(TestJobs.Running() with { Stage = "place_plants" });
        using var client = factory.CreateClient();

        var html = await client.GetStringAsync($"/Jobs/Details/{TestJobs.RunningId}");

        Assert.DoesNotContain("http-equiv=\"refresh\"", html);
        Assert.Contains("выполняется", html);
        Assert.Contains("Этап 3 из 7: Размещение посадок.", html);
        Assert.Contains($"data-status-url=\"/jobs/{TestJobs.RunningId}/status\"", html);
        Assert.Contains("/js/job-status.js", html);
    }

    [Fact]
    public async Task FinishedJobPageDoesNotPoll()
    {
        using var factory = new GreenPlanWebFactory();
        using var client = factory.CreateClient();

        var html = await client.GetStringAsync($"/Jobs/Details/{TestJobs.SucceededId}");

        Assert.DoesNotContain("/js/job-status.js", html);
    }

    [Fact]
    public async Task StatusEndpointReturnsCompactProgress()
    {
        using var factory = new GreenPlanWebFactory();
        factory.Engine.Jobs.Add(TestJobs.Running() with { Stage = "verify" });
        using var client = factory.CreateClient();

        using var response = await client.GetAsync($"/jobs/{TestJobs.RunningId}/status");
        using var status = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
        using var missing = await client.GetAsync("/jobs/unknown/status");

        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal("no-store", response.Headers.CacheControl?.ToString());
        Assert.Equal("running", status.RootElement.GetProperty("status").GetString());
        Assert.False(status.RootElement.GetProperty("finished").GetBoolean());
        Assert.Equal("Этап 7 из 7: Независимая проверка.", status.RootElement.GetProperty("progressText").GetString());
        Assert.Equal(HttpStatusCode.NotFound, missing.StatusCode);
    }

    [Fact]
    public async Task StatusEndpointMarksFinishedJobs()
    {
        using var factory = new GreenPlanWebFactory();
        using var client = factory.CreateClient();

        using var status = JsonDocument.Parse(await client.GetStringAsync($"/jobs/{TestJobs.SucceededId}/status"));

        Assert.True(status.RootElement.GetProperty("finished").GetBoolean());
        Assert.Equal("готово", status.RootElement.GetProperty("statusText").GetString());
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
        byte[]? drawing = null,
        string? territory = null)
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

        if (territory is not null)
        {
            content.Add(new StringContent(territory, Encoding.UTF8), "Form.Territory");
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
