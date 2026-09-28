using System.Text.Json;
using GreenPlan.Web.Forms;

namespace GreenPlan.Web.Tests;

public sealed class RunSettingsFormTests
{
    [Fact]
    public void DefaultsProduceNoOverrides()
    {
        var form = new RunSettingsForm();

        Assert.Null(form.ToJson());
        Assert.Equal(0, form.ChangedCount);
    }

    [Fact]
    public void SwitchesMapToTheEngineSections()
    {
        var form = new RunSettingsForm
        {
            ShrubMasses = false,
            HedgesAlongRows = false,
            RootBarriers = false,
            TreePalette = 4,
            ProtectionZones = true,
        };

        using var json = JsonDocument.Parse(form.ToJson()!);
        var root = json.RootElement;
        var composition = root.GetProperty("placement").GetProperty("composition");

        Assert.Equal(0, composition.GetProperty("shrub_mass_radii_m").GetArrayLength());
        Assert.Equal(1.0, composition.GetProperty("hedge_companion_weight").GetDouble());
        Assert.False(root.GetProperty("design").GetProperty("allow_root_barriers").GetBoolean());
        Assert.False(root.GetProperty("placement").GetProperty("allow_conditional").GetBoolean());
        Assert.True(root.GetProperty("design").GetProperty("apply_protection_zones").GetBoolean());
        Assert.Equal(4, root.GetProperty("species").GetProperty("tree_palette_size").GetInt32());
        Assert.Equal(5, form.ChangedCount - 1);
    }
}
