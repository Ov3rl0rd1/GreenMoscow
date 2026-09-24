using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using GreenPlan.Web.Models;

namespace GreenPlan.Web.Services;

public sealed class EngineClient(HttpClient http) : IEngineClient
{
    public const string JobsPath = "api/v1/jobs";
    public const string TerritoriesPath = "api/v1/territories";
    public const string HealthPath = "healthz";
    private const string DefaultContentType = "application/octet-stream";
    private const string DetailProperty = "detail";
    private const string UnavailableMessage = "Сервис расчёта недоступен.";
    private const string TimeoutMessage = "Сервис расчёта не ответил вовремя.";
    private const string EmptyResponseMessage = "Сервис расчёта вернул пустой ответ.";

    public static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
    };

    public async Task<JobDto> CreateJobAsync(JobSubmission submission, CancellationToken cancellationToken)
    {
        using var content = BuildJobContent(submission);
        using var response = await SendAsync(token => http.PostAsync(JobsPath, content, token), cancellationToken);
        await EnsureSuccessAsync(response, cancellationToken);
        return await ReadJsonAsync<JobDto>(response, cancellationToken);
    }

    public async Task<JobDto?> GetJobAsync(string jobId, CancellationToken cancellationToken)
    {
        using var response = await SendAsync(token => http.GetAsync(JobPath(jobId), token), cancellationToken);
        if (response.StatusCode == HttpStatusCode.NotFound)
        {
            return null;
        }

        await EnsureSuccessAsync(response, cancellationToken);
        return await ReadJsonAsync<JobDto>(response, cancellationToken);
    }

    public async Task<IReadOnlyList<JobDto>> ListJobsAsync(CancellationToken cancellationToken)
    {
        using var response = await SendAsync(token => http.GetAsync(JobsPath, token), cancellationToken);
        await EnsureSuccessAsync(response, cancellationToken);
        return await ReadJsonAsync<List<JobDto>>(response, cancellationToken);
    }

    public async Task<IReadOnlyList<TerritoryDto>> ListTerritoriesAsync(CancellationToken cancellationToken)
    {
        using var response = await SendAsync(token => http.GetAsync(TerritoriesPath, token), cancellationToken);
        await EnsureSuccessAsync(response, cancellationToken);
        return await ReadJsonAsync<List<TerritoryDto>>(response, cancellationToken);
    }

    public async Task<EngineArtifact?> GetArtifactAsync(string jobId, string name, CancellationToken cancellationToken)
    {
        var path = $"{JobPath(jobId)}/artifacts/{Uri.EscapeDataString(name)}";
        using var response = await SendAsync(token => http.GetAsync(path, token), cancellationToken);
        if (response.StatusCode == HttpStatusCode.NotFound)
        {
            return null;
        }

        await EnsureSuccessAsync(response, cancellationToken);
        var content = await response.Content.ReadAsByteArrayAsync(cancellationToken);
        var contentType = response.Content.Headers.ContentType?.MediaType ?? DefaultContentType;
        return new EngineArtifact(content, contentType);
    }

    public async Task<HealthDto?> GetHealthAsync(CancellationToken cancellationToken)
    {
        try
        {
            using var response = await http.GetAsync(HealthPath, cancellationToken);
            return response.IsSuccessStatusCode ? await ReadJsonAsync<HealthDto>(response, cancellationToken) : null;
        }
        catch (HttpRequestException)
        {
            return null;
        }
        catch (TaskCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            return null;
        }
    }

    private static MultipartFormDataContent BuildJobContent(JobSubmission submission)
    {
        var content = new MultipartFormDataContent();
        foreach (var drawing in submission.Drawings)
        {
            var part = new StreamContent(drawing.Content);
            part.Headers.ContentType = new MediaTypeHeaderValue(DefaultContentType);
            content.Add(part, "drawing", drawing.FileName);
        }

        content.Add(new StringContent(submission.Title), "title");
        if (!string.IsNullOrWhiteSpace(submission.Territory))
        {
            content.Add(new StringContent(submission.Territory), "territory");
        }

        if (!string.IsNullOrWhiteSpace(submission.Guidance))
        {
            content.Add(new StringContent(submission.Guidance), "guidance");
        }

        if (!string.IsNullOrWhiteSpace(submission.MainFile))
        {
            content.Add(new StringContent(submission.MainFile), "main_file");
        }

        if (!string.IsNullOrWhiteSpace(submission.ConfigYaml))
        {
            content.Add(new StringContent(submission.ConfigYaml), "config", "config.yaml");
        }

        return content;
    }

    private static async Task<HttpResponseMessage> SendAsync(
        Func<CancellationToken, Task<HttpResponseMessage>> send,
        CancellationToken cancellationToken)
    {
        try
        {
            return await send(cancellationToken);
        }
        catch (HttpRequestException error)
        {
            throw new EngineRequestException(UnavailableMessage, error);
        }
        catch (TaskCanceledException error) when (!cancellationToken.IsCancellationRequested)
        {
            throw new EngineRequestException(TimeoutMessage, error);
        }
    }

    private static async Task EnsureSuccessAsync(HttpResponseMessage response, CancellationToken cancellationToken)
    {
        if (response.IsSuccessStatusCode)
        {
            return;
        }

        var detail = await ReadDetailAsync(response, cancellationToken);
        throw new EngineRequestException($"Сервис расчёта вернул {(int)response.StatusCode}: {detail}");
    }

    private static async Task<string> ReadDetailAsync(HttpResponseMessage response, CancellationToken cancellationToken)
    {
        var text = await response.Content.ReadAsStringAsync(cancellationToken);
        try
        {
            using var document = JsonDocument.Parse(text);
            return document.RootElement.TryGetProperty(DetailProperty, out var detail) ? detail.ToString() : text;
        }
        catch (JsonException)
        {
            return text;
        }
    }

    private static async Task<T> ReadJsonAsync<T>(HttpResponseMessage response, CancellationToken cancellationToken)
    {
        var value = await response.Content.ReadFromJsonAsync<T>(JsonOptions, cancellationToken);
        return value ?? throw new EngineRequestException(EmptyResponseMessage);
    }

    private static string JobPath(string jobId) => $"{JobsPath}/{Uri.EscapeDataString(jobId)}";
}
