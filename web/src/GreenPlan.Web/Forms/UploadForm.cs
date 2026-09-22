using System.ComponentModel.DataAnnotations;

namespace GreenPlan.Web.Forms;

public sealed class UploadForm
{
    public const int MaxTitleLength = 200;

    [MinLength(1, ErrorMessage = "Выберите чертёж: хотя бы один .dxf/.dwg или архив папки объекта.")]
    [Display(Name = "Чертежи объекта: один или несколько .dxf/.dwg (генплан, подоснова) или архив папки (.zip)")]
    public List<IFormFile> Drawing { get; set; } = [];

    [Required(ErrorMessage = "Укажите название участка.")]
    [StringLength(MaxTitleLength)]
    [Display(Name = "Название участка")]
    public string Title { get; set; } = "Участок";

    [Display(Name = "Главный чертёж (имя файла или путь в архиве; если не указан — выбирается автоматически)")]
    public string? MainFile { get; set; }

    [Display(Name = "Категория территории")]
    public string? Territory { get; set; }

    [Display(Name = "Настройки прогона (YAML, необязательно)")]
    public IFormFile? Config { get; set; }
}
