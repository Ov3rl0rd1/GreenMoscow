namespace GreenPlan.Web.Tests.Support;

public sealed record RecordedRequest(HttpMethod Method, string Path, string? Body);

public sealed class FakeHttpMessageHandler(Func<HttpRequestMessage, HttpResponseMessage> respond) : HttpMessageHandler
{
    public List<RecordedRequest> Requests { get; } = [];

    public static FakeHttpMessageHandler Returning(System.Net.HttpStatusCode status, string body, string contentType = "application/json") =>
        new(_ => new HttpResponseMessage(status)
        {
            Content = new StringContent(body, System.Text.Encoding.UTF8, contentType),
        });

    public static FakeHttpMessageHandler Throwing(Exception error) => new(_ => throw error);

    protected override async Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request,
        CancellationToken cancellationToken)
    {
        var body = request.Content is null ? null : await request.Content.ReadAsStringAsync(cancellationToken);
        Requests.Add(new RecordedRequest(request.Method, request.RequestUri?.PathAndQuery ?? string.Empty, body));
        return respond(request);
    }
}
