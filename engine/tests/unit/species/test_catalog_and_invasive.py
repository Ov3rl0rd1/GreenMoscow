from pathlib import Path

import pytest
import yaml

from greenplan.domain.norms import SHRUB, TREE
from greenplan.knowledge.invasive_registry import (
    ALLOWED,
    ALLOWED_WITH_CONTROL,
    CONDITIONAL,
    EXCLUDED,
    InvasiveRegistry,
    latin_key,
)
from greenplan.knowledge.plant_catalog import LIMITED_STREET_SUITABILITY, NOT_STREET_SUITABLE, PlantCatalog

from fixtures.species_factory import species


@pytest.fixture(scope="module")
def real_catalog(knowledge_root: Path) -> PlantCatalog:
    return PlantCatalog.from_file(knowledge_root / "plants" / "assortment.yaml")


@pytest.fixture(scope="module")
def registry(knowledge_root: Path) -> InvasiveRegistry:
    return InvasiveRegistry.from_file(knowledge_root / "plants" / "invasive_moscow.yaml")


def test_assortment_species_are_loaded_with_targets(real_catalog: PlantCatalog) -> None:
    linden = real_catalog.get("tilia_cordata")
    assert len(real_catalog.species()) >= 30
    assert (linden.target, linden.crown_diameter_m, linden.heating_min_axis_m) == (TREE, 10.0, 2.0)
    assert real_catalog.get("cotoneaster_lucidus").target == SHRUB
    assert real_catalog.get("juniperus_sabina").target is None


def test_reference_usage_counts_are_summed(real_catalog: PlantCatalog) -> None:
    assert real_catalog.get("spiraea").reference_usage_total == 699 + 397 + 1325


def test_selection_rules_are_loaded(real_catalog: PlantCatalog) -> None:
    street = real_catalog.rule("street_carriageway_adjacent")
    assert "tilia_europaea_pallida" in street.prefer
    assert "quercus_robur" in street.avoid
    assert real_catalog.rule("under_overhead_line").max_height_m == 4.0
    assert real_catalog.rule("near_heating_network").source_ref == "tsn_p4_2_8"


def test_street_suitability_is_normalized(real_catalog: PlantCatalog) -> None:
    assert real_catalog.get("quercus_robur").street_suitability == NOT_STREET_SUITABLE
    assert real_catalog.get("betula_pendula").street_suitability == LIMITED_STREET_SUITABILITY


def test_latin_keys_use_genus_and_species_or_genus_for_spp() -> None:
    assert latin_key("Acer negundo") == "acer negundo"
    assert latin_key("Reynoutria spp.") == "reynoutria"
    assert latin_key("Reynoutria bohemica / R. japonica") == "reynoutria bohemica"


def test_group_three_species_are_allowed_with_spread_control(
    registry: InvasiveRegistry, real_catalog: PlantCatalog
) -> None:
    verdict = registry.verdict(real_catalog.get("cornus_alba"))
    assert verdict.status == ALLOWED_WITH_CONTROL
    assert "ppm369_invasive" in verdict.source_refs
    assert verdict.groups == ("369-ПП:III",)
    for key in ("rosa_rugosa", "physocarpus_opulifolius"):
        assert registry.verdict(real_catalog.get(key)).status == ALLOWED_WITH_CONTROL


def test_species_marked_as_disputed_in_the_assortment_stays_conditional(registry: InvasiveRegistry) -> None:
    disputed = species("disputed", latin="Syringa vulgaris", invasive_status="conflicting_local_list")
    assert registry.verdict(disputed).status == CONDITIONAL


def test_moscow_list_matches_the_official_appendix(knowledge_root: Path) -> None:
    content = yaml.safe_load((knowledge_root / "plants" / "invasive_moscow.yaml").read_text(encoding="utf-8"))
    groups = content["moscow_369pp"]["groups"]
    sizes = {name: len(data["species"]) for name, data in groups.items()}
    assert sizes == {"I": 6, "II": 1, "III": 14, "IV": 11}
    assert all(data["verification"] == "verified" for data in groups.values())


def test_unlisted_species_are_allowed(registry: InvasiveRegistry, real_catalog: PlantCatalog) -> None:
    assert registry.verdict(real_catalog.get("cornus_sericea")).status == ALLOWED
    assert registry.verdict(real_catalog.get("tilia_europaea_pallida")).status == ALLOWED


def test_group_two_and_federal_species_are_excluded(registry: InvasiveRegistry) -> None:
    verdict = registry.verdict(species("negundo", latin="Acer negundo"))
    assert verdict.status == EXCLUDED
    assert set(verdict.source_refs) == {"ppm369_invasive", "mpr77_invasive"}


def test_genus_listing_matches_every_species_of_genus(registry: InvasiveRegistry) -> None:
    assert registry.verdict(species("knotweed", latin="Reynoutria japonica")).status == EXCLUDED


def test_no_assortment_species_is_excluded_outright(
    registry: InvasiveRegistry, real_catalog: PlantCatalog
) -> None:
    assert all(registry.verdict(item).status != EXCLUDED for item in real_catalog.species())
