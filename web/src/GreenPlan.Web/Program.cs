using System.Text.Encodings.Web;
using System.Text.Unicode;
using GreenPlan.Web.Endpoints;
using GreenPlan.Web.Options;
using GreenPlan.Web.Services;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.Extensions.Options;

var builder = WebApplication.CreateBuilder(args);
var engineSection = builder.Configuration.GetSection(EngineOptions.SectionName);
var engineOptions = engineSection.Get<EngineOptions>() ?? new EngineOptions();

builder.Services.Configure<EngineOptions>(engineSection);
builder.Services.Configure<FormOptions>(options => options.MultipartBodyLengthLimit = engineOptions.MaxUploadBytes);
builder.WebHost.ConfigureKestrel(options => options.Limits.MaxRequestBodySize = engineOptions.MaxUploadBytes);
builder.Services.AddSingleton(HtmlEncoder.Create(UnicodeRanges.BasicLatin, UnicodeRanges.Latin1Supplement, UnicodeRanges.Cyrillic, UnicodeRanges.GeneralPunctuation));
builder.Services.AddRazorPages();
builder.Services.AddSingleton(TimeProvider.System);
builder.Services.AddHttpClient<IEngineClient, EngineClient>((services, client) =>
{
    var options = services.GetRequiredService<IOptions<EngineOptions>>().Value;
    client.BaseAddress = options.BaseUri;
    client.Timeout = options.Timeout;
});

var app = builder.Build();

app.UseStaticFiles();
app.UseRouting();
app.UseAntiforgery();
app.MapRazorPages();
app.MapArtifactEndpoints();
app.MapJobStatusEndpoints();
app.MapGet("/healthz", () => Results.Ok(new { status = "ok" }));

app.Run();

public partial class Program
{
}
