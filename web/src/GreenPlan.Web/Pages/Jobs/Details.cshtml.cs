using GreenPlan.Web.Models;
using GreenPlan.Web.Presentation;
using GreenPlan.Web.Services;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;

namespace GreenPlan.Web.Pages.Jobs;

public sealed class DetailsModel(IEngineClient engine, TimeProvider clock) : PageModel
{
    public JobDto? Job { get; private set; }

    public JobTimeline? Timeline { get; private set; }

    public async Task<IActionResult> OnGetAsync(string id, CancellationToken cancellationToken)
    {
        Job = await engine.GetJobAsync(id, cancellationToken);
        if (Job is null)
        {
            return NotFound();
        }

        Timeline = JobTimeline.From(Job, clock.GetUtcNow());
        return Page();
    }
}
