using System.ComponentModel.DataAnnotations;
using System.Text.Json;

namespace GreenPlan.Web.Forms;

public sealed class RunSettingsForm
{
    public const string UpperBound = "upper";
    public const string LowerBound = "lower";

    private static readonly RunSettingsForm Defaults = new();

    [Range(0, 100, ErrorMessage = "Минимум деревьев — от 0 до 100 % норматива.")]
    [Display(Name = "Минимум деревьев, % от норматива")]
    public int MinTreeSharePercent { get; set; } = 30;

    [Display(Name = "Композиция как у проектировщика")]
    public bool Composition { get; set; } = true;

    [Range(0, 100, ErrorMessage = "Доля деревьев в рядах — от 0 до 100 %.")]
    [Display(Name = "Деревья в рядах, % от количества")]
    public int TreeRowSharePercent { get; set; } = 60;

    [Range(0, 100, ErrorMessage = "Доля кустарника в изгородях — от 0 до 100 %.")]
    [Display(Name = "Кустарник в изгородях и полосах, %")]
    public int HedgeSharePercent { get; set; } = 50;

    [Display(Name = "Крупные массивы кустарника")]
    public bool ShrubMasses { get; set; } = true;

    [Display(Name = "Живая изгородь вдоль рядов деревьев")]
    public bool HedgesAlongRows { get; set; } = true;

    [Display(Name = "Агенты дорабатывают план")]
    public bool Agents { get; set; } = true;

    [Range(0, 60, ErrorMessage = "Резерв агентов — от 0 до 60 %.")]
    [Display(Name = "Резерв для агентов, % от количества")]
    public int AgentReservePercent { get; set; } = 25;

    [Display(Name = "Посадки с корнезащитой рядом с сетями")]
    public bool RootBarriers { get; set; } = true;

    [Display(Name = "Учитывать охранные зоны ООПТ")]
    public bool ProtectionZones { get; set; }

    [Range(0.4, 750, ErrorMessage = "Напряжение ЛЭП — от 0,4 до 750 кВ.")]
    [Display(Name = "Напряжение ЛЭП без подписи, кВ")]
    public double OverheadVoltageKv { get; set; } = 10;

    [RegularExpression("upper|lower", ErrorMessage = "Выберите верхнюю или нижнюю границу диапазонов норм.")]
    [Display(Name = "Диапазоны норм плотности и шага")]
    public string RangeBound { get; set; } = UpperBound;

    [Range(1, 12, ErrorMessage = "Пород деревьев в палитре — от 1 до 12.")]
    [Display(Name = "Пород деревьев в палитре")]
    public int TreePalette { get; set; } = 6;

    [Range(1, 12, ErrorMessage = "Пород кустарника в палитре — от 1 до 12.")]
    [Display(Name = "Пород кустарника в палитре")]
    public int ShrubPalette { get; set; } = 6;

    [Display(Name = "Допускать условно подходящие породы")]
    public bool ConditionalSpecies { get; set; }

    public int ChangedCount => Changes().Count;

    public string? ToJson()
    {
        var changes = Changes();
        if (changes.Count == 0)
        {
            return null;
        }

        var root = new Dictionary<string, object>();
        foreach (var (path, value) in changes)
        {
            var node = root;
            foreach (var key in path[..^1])
            {
                if (!node.TryGetValue(key, out var child))
                {
                    child = new Dictionary<string, object>();
                    node[key] = child;
                }

                node = (Dictionary<string, object>)child;
            }

            node[path[^1]] = value;
        }

        return JsonSerializer.Serialize(root);
    }

    private List<(string[] Path, object Value)> Changes()
    {
        var changes = new List<(string[] Path, object Value)>();

        void Add(bool changed, object value, params string[] path)
        {
            if (changed)
            {
                changes.Add((path, value));
            }
        }

        Add(MinTreeSharePercent != Defaults.MinTreeSharePercent, MinTreeSharePercent / 100.0, "placement", "min_tree_count_share");
        Add(Composition != Defaults.Composition, Composition, "placement", "composition", "enabled");
        Add(TreeRowSharePercent != Defaults.TreeRowSharePercent, TreeRowSharePercent / 100.0, "placement", "composition", "tree_row_budget_share");
        Add(HedgeSharePercent != Defaults.HedgeSharePercent, HedgeSharePercent / 100.0, "placement", "composition", "hedge_budget_share");
        Add(ShrubMasses != Defaults.ShrubMasses, Array.Empty<double>(), "placement", "composition", "shrub_mass_radii_m");
        Add(HedgesAlongRows != Defaults.HedgesAlongRows, 1.0, "placement", "composition", "hedge_companion_weight");
        Add(Agents != Defaults.Agents, Agents, "placement", "coordinator", "enabled");
        Add(AgentReservePercent != Defaults.AgentReservePercent, AgentReservePercent / 100.0, "placement", "composition", "reserve_share");
        Add(RootBarriers != Defaults.RootBarriers, RootBarriers, "design", "allow_root_barriers");
        Add(RootBarriers != Defaults.RootBarriers, RootBarriers, "placement", "allow_conditional");
        Add(ProtectionZones != Defaults.ProtectionZones, ProtectionZones, "design", "apply_protection_zones");
        Add(Math.Abs(OverheadVoltageKv - Defaults.OverheadVoltageKv) > 1e-9, OverheadVoltageKv, "design", "unknown_overhead_voltage_kv");
        Add(RangeBound != Defaults.RangeBound, RangeBound, "placement", "range_bound");
        Add(TreePalette != Defaults.TreePalette, TreePalette, "species", "tree_palette_size");
        Add(ShrubPalette != Defaults.ShrubPalette, ShrubPalette, "species", "shrub_palette_size");
        Add(ConditionalSpecies != Defaults.ConditionalSpecies, ConditionalSpecies, "species", "allow_conditional_species");
        return changes;
    }
}
