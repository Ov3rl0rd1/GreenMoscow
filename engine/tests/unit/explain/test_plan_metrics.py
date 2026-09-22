from pathlib import Path

import pytest
from shapely.geometry import LineString, box

from greenplan.domain.norms import SHRUB, TREE
from greenplan.domain.obstacle_kinds import CARRIAGEWAY_EDGE
from greenplan.domain.site import Obstacle, SiteDiagnostics, SiteModel
from greenplan.explain.explanation_model import PlantExplanation, SpeciesView
from greenplan.explain.plan_metrics import CostCatalog, plan_metrics, volume_statement


def species_view(key: str, name_ru: str) -> SpeciesView:
    return SpeciesView(key, name_ru, "", 5.0, 10.0, "allowed", "", (), ())


def plant(key: str, name_ru: str, plant_type: str, x: float, y: float, crown: float) -> PlantExplanation:
    return PlantExplanation(
        plant_id=f"{key}-{x}",
        status="accepted",
        plant_type=plant_type,
        x=x,
        y=y,
        crown_diameter_m=crown,
        species=species_view(key, name_ru),
        clearances=(),
        violations=(),
        explanation_ru="",
    )


def street_site() -> SiteModel:
    edge = Obstacle(CARRIAGEWAY_EDGE, LineString([(0, 0), (100, 0)]), "surfaces", "edges", ("surface",))
    lawn = box(0, 2, 100, 12)
    return SiteModel(lawn, lawn, (edge,), (), (), SiteDiagnostics())


def plants() -> list[PlantExplanation]:
    return [
        plant("tilia", "Липа мелколистная", TREE, 10.0, 5.0, 8.0),
        plant("tilia", "Липа мелколистная", TREE, 20.0, 5.0, 8.0),
        plant("acer", "Клён остролистный", TREE, 90.0, 5.0, 8.0),
        plant("spiraea", "Спирея", SHRUB, 12.0, 4.0, 1.5),
    ]


def test_species_count_and_dominant_share() -> None:
    metrics = plan_metrics(street_site(), plants(), ["tilia"])
    assert metrics.species_count == 3
    assert metrics.max_species_share == pytest.approx(0.5)
    assert metrics.listed_species_share == pytest.approx(0.5)


def test_tiers_list_trees_shrubs_and_lawn() -> None:
    assert plan_metrics(street_site(), plants(), []).tiers == (
        "деревья",
        "кустарники",
        "газон и почвопокровные",
    )


def test_crown_projection_uses_crown_diameters() -> None:
    metrics = plan_metrics(street_site(), plants(), [])
    expected = 3 * 3.14159 * 16 + 3.14159 * 0.5625
    assert metrics.crown_projection_m2 == pytest.approx(expected, rel=1e-3)
    assert 0 < metrics.crown_share_of_plantable < 1


def test_street_front_is_measured_under_the_canopy() -> None:
    metrics = plan_metrics(street_site(), plants(), [])
    assert 0 < metrics.street_front_covered_m < 100
    assert metrics.street_front_covered_m > 20


def test_plan_without_trees_covers_no_street_front() -> None:
    shrubs = [plant("spiraea", "Спирея", SHRUB, 12.0, 4.0, 1.5)]
    assert plan_metrics(street_site(), shrubs, []).street_front_covered_m == 0.0


def test_volume_statement_counts_plants_and_areas() -> None:
    volumes = volume_statement(plants(), lawn_area_m2=1000.0, root_barrier_length_m=12.5)
    assert volumes.trees == 3
    assert volumes.shrubs == 1
    assert volumes.plants[0].count == 2
    assert volumes.lawn_area_m2 == 1000.0
    assert volumes.root_barrier_length_m == 12.5


def test_cost_estimate_compares_with_the_reference_range(knowledge_root: Path) -> None:
    catalog = CostCatalog.from_knowledge(knowledge_root)
    volumes = volume_statement(plants(), lawn_area_m2=1000.0, root_barrier_length_m=10.0)
    estimate = catalog.estimate(volumes, plantable_area_m2=1000.0, category_id="district_street")
    assert estimate.total_rub > 0
    assert estimate.per_hectare_rub == pytest.approx(estimate.total_rub * 10)
    assert estimate.reference_range_rub == (10000000.0, 25000000.0)
    assert estimate.within_reference_range is not None


def test_cost_without_a_known_category_has_no_reference(knowledge_root: Path) -> None:
    catalog = CostCatalog.from_knowledge(knowledge_root)
    volumes = volume_statement(plants(), lawn_area_m2=1000.0, root_barrier_length_m=0.0)
    estimate = catalog.estimate(volumes, plantable_area_m2=1000.0, category_id="park")
    assert estimate.reference_range_rub is None
    assert estimate.within_reference_range is None
