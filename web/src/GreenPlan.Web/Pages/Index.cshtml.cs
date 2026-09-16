using GreenPlan.Web.Forms;
using GreenPlan.Web.Models;
using GreenPlan.Web.Services;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;

namespace GreenPlan.Web.Pages;

public sealed class IndexModel(IEngineClient engine) : PageModel
{
    [BindProperty]
    public UploadForm Form { get; set; } = new();

    public IReadOnlyList<JobDto> Jobs { get; private set; } = [];

    public bool EngineAvailable { get; private set; }

    public string? ErrorMessage { get; private set; }

    public async Task OnGetAsync(CancellationToken cancellationToken)
    {
        await LoadOverviewAsync(cancellationToken);
    }

    public async Task<IActionResult> OnPostAsync(CancellationToken cancellationToken)
    {
        if (!ModelState.IsValid || Form.Drawing is null)
        {
            await LoadOverviewAsync(cancellationToken);
            return Page();
        }

        try
        {
            var job = await SubmitAsync(Form.Drawing, cancellationToken);
            return RedirectToPage("/Jobs/Details", new { id = job.JobId });
        }
        catch (EngineRequestException error)
        {
            ErrorMessage = error.Message;
            await LoadOverviewAsync(cancellationToken);
            return Page();
        }
    }

    private async Task<JobDto> SubmitAsync(IFormFile drawing, CancellationToken cancellationToken)
    {
        await using var drawingStream = drawing.OpenReadStream();
        var configYaml = await ReadTextAsync(Form.Config, cancellationToken);
        var submission = new JobSubmission(drawingStream, drawing.FileName, Form.Title, Form.MainFile, configYaml);
        return await engine.CreateJobAsync(submission, cancellationToken);
    }

    private async Task LoadOverviewAsync(CancellationToken cancellationToken)
    {
        EngineAvailable = await engine.GetHealthAsync(cancellationToken) is not null;
        if (!EngineAvailable)
        {
            return;
        }

        try
        {
            Jobs = await engine.ListJobsAsync(cancellationToken);
        }
        catch (EngineRequestException error)
        {
            ErrorMessage ??= error.Message;
        }
    }

    private static async Task<string?> ReadTextAsync(IFormFile? file, CancellationToken cancellationToken)
    {
        if (file is null)
        {
            return null;
        }

        using var reader = new StreamReader(file.OpenReadStream());
        return await reader.ReadToEndAsync(cancellationToken);
    }
}
