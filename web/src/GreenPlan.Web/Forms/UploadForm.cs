using System.ComponentModel.DataAnnotations;

namespace GreenPlan.Web.Forms;

public sealed class UploadForm
{
    public const int MaxTitleLength = 200;

    [MinLength(1, ErrorMessage = "Выберите чертёж: хотя бы один .dxf/.dwg или архив папки объекта.")]
    [Display(Name = "Чертежи объекта")]
    public List<IFormFile> Drawing { get; set; } = [];

    [Required(ErrorMessage = "Укажите название участка.")]
    [StringLength(MaxTitleLength)]
    [Display(Name = "Название участка")]
    public string Title { get; set; } = "Участок";

    [Display(Name = "Главный чертёж")]
    public string? MainFile { get; set; }

    [Display(Name = "Категория территории")]
    public string? Territory { get; set; }

    [Display(Name = "Места и количество предлагает модель, обученная на проектах датасета")]
    public bool UseModel { get; set; } = true;

    [Display(Name = "Разрешить превышать рекомендательный норматив плотности (ТСН 30-307)")]
    public bool ExceedDensity { get; set; }

    [Display(Name = "Файл настроек YAML")]
    public IFormFile? Config { get; set; }

    public RunSettingsForm Settings { get; set; } = new();
}
