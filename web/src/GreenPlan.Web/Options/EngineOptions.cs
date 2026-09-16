namespace GreenPlan.Web.Options;

public sealed class EngineOptions
{
    public const string SectionName = "Engine";

    public string BaseUrl { get; set; } = "http://localhost:8000/";

    public TimeSpan Timeout { get; set; } = TimeSpan.FromMinutes(10);

    public long MaxUploadBytes { get; set; } = 2L * 1024 * 1024 * 1024;

    public Uri BaseUri => new(BaseUrl.EndsWith('/') ? BaseUrl : BaseUrl + "/");
}
