using System.ComponentModel.DataAnnotations;

namespace GreenPlan.Web.Forms;

public sealed class UploadForm
{
    public const int MaxTitleLength = 200;

    [Required(ErrorMessage = "Выберите чертёж или архив папки объекта.")]
    [Display(Name = "Чертёж (.dxf, .dwg) или архив папки объекта (.zip)")]
    public IFormFile? Drawing { get; set; }

    [Required(ErrorMessage = "Укажите название участка.")]
    [StringLength(MaxTitleLength)]
    [Display(Name = "Название участка")]
    public string Title { get; set; } = "Участок";

    [Display(Name = "Главный чертёж внутри архива (путь, если чертежей несколько)")]
    public string? MainFile { get; set; }

    [Display(Name = "Настройки прогона (YAML, необязательно)")]
    public IFormFile? Config { get; set; }
}
