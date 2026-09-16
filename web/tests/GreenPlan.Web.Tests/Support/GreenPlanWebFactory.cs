using GreenPlan.Web.Services;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;

namespace GreenPlan.Web.Tests.Support;

public sealed class GreenPlanWebFactory : WebApplicationFactory<Program>
{
    public FakeEngineClient Engine { get; } = new();

    public HttpClient CreateNonRedirectingClient() =>
        CreateClient(new WebApplicationFactoryClientOptions { AllowAutoRedirect = false });

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.UseEnvironment("Testing");
        builder.ConfigureTestServices(services =>
        {
            services.RemoveAll<IEngineClient>();
            services.AddSingleton<IEngineClient>(Engine);
        });
    }
}
