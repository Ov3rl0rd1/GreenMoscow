using GreenPlan.Web.Models;
using GreenPlan.Web.Services;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;

namespace GreenPlan.Web.Pages.Jobs;

public sealed class DetailsModel(IEngineClient engine) : PageModel
{
    public JobDto? Job { get; private set; }

    public async Task<IActionResult> OnGetAsync(string id, CancellationToken cancellationToken)
    {
        Job = await engine.GetJobAsync(id, cancellationToken);
        return Job is null ? NotFound() : Page();
    }
}
