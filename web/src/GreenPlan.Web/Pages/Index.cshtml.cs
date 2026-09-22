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

    public IReadOnlyList<TerritoryDto> Territories { get; private set; } = [];

    public bool EngineAvailable { get; private set; }

    public string? ErrorMessage { get; private set; }

    public async Task OnGetAsync(CancellationToken cancellationToken)
    {
        await LoadOverviewAsync(cancellationToken);
    }

    public async Task<IActionResult> OnPostAsync(CancellationToken cancellationToken)
    {
        if (!ModelState.IsValid || Form.Drawing.Count == 0)
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

    private async Task<JobDto> SubmitAsync(IReadOnlyList<IFormFile> drawings, CancellationToken cancellationToken)
    {
        var uploads = drawings.Select(file => new UploadedDrawing(file.OpenReadStream(), file.FileName)).ToList();
        try
        {
            var configYaml = await ReadTextAsync(Form.Config, cancellationToken);
            var submission = new JobSubmission(uploads, Form.Title, Form.MainFile, configYaml, Form.Territory);
            return await engine.CreateJobAsync(submission, cancellationToken);
        }
        finally
        {
            foreach (var upload in uploads)
            {
                await upload.Content.DisposeAsync();
            }
        }
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
            Territories = await engine.ListTerritoriesAsync(cancellationToken);
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
