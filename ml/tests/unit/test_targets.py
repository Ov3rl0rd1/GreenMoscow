import numpy as np
import pytest
from shapely.geometry import Point

from greenplan.domain.norms import SHRUB, TREE
from greenplan.knowledge.plant_catalog import PlantCatalog, Species
from greenplan.placement.raster import RasterGrid
from greenplan_ml.reference_extractor import ReferencePlanting
from greenplan_ml.targets import (
    CROWN_CHANNEL_INDEX,
    SHRUB_CHANNEL_INDEX,
    TARGET_CHANNEL_COUNT,
    TREE_CHANNEL_INDEX,
    SpeciesCrownLookup,
    TargetSettings,
    TargetStackBuilder,
    planting_counts,
    splat,
)

GRID = RasterGrid(0.0, 0.0, 0.5, 40, 40)
SETTINGS = TargetSettings()


def catalog() -> PlantCatalog:
    return PlantCatalog(
        [
            Species("tilia", "Липа мелколистная", "Tilia cordata", "tree", 8.0, 20.0),
            Species("cotoneaster", "Кизильник блестящий", "Cotoneaster lucidus", "shrub", 1.2, 2.0),
        ]
    )


def builder() -> TargetStackBuilder:
    return TargetStackBuilder(SpeciesCrownLookup(catalog(), SETTINGS), SETTINGS)


def planting_at(x: float, y: float, target: str, species: str) -> ReferencePlanting:
    return ReferencePlanting(Point(x, y), target, "tree", species, "layer", "scheme")


def test_single_impulse_keeps_a_unit_peak() -> None:
    impulses = np.zeros((20, 20), dtype=np.float32)
    impulses[10, 10] = 1.0
    assert splat(impulses, 2.0).max() == pytest.approx(1.0, abs=0.02)


def test_empty_impulses_stay_empty() -> None:
    impulses = np.zeros((4, 4), dtype=np.float32)
    assert not splat(impulses, 1.5).any()


def test_trees_and_shrubs_land_on_their_own_channels() -> None:
    plantings = [
        planting_at(5.0, 5.0, TREE, "Липа мелколистная"),
        planting_at(15.0, 15.0, SHRUB, "Кизильник блестящий"),
    ]
    stack = builder().build(GRID, plantings)
    assert stack.shape == (TARGET_CHANNEL_COUNT, GRID.rows, GRID.columns)
    assert stack[TREE_CHANNEL_INDEX, 10, 10] == pytest.approx(1.0, abs=0.05)
    assert stack[TREE_CHANNEL_INDEX, 30, 30] == pytest.approx(0.0, abs=0.01)
    assert stack[SHRUB_CHANNEL_INDEX, 30, 30] == pytest.approx(1.0, abs=0.05)


def test_crown_channel_scales_the_catalogue_diameter() -> None:
    stack = builder().build(GRID, [planting_at(5.0, 5.0, TREE, "Липа мелколистная")])
    assert stack[CROWN_CHANNEL_INDEX, 10, 10] == pytest.approx(8.0 / SETTINGS.crown_saturation_m, abs=0.02)


def test_crown_channel_is_zero_where_nothing_is_planted() -> None:
    stack = builder().build(GRID, [planting_at(5.0, 5.0, TREE, "Липа мелколистная")])
    assert stack[CROWN_CHANNEL_INDEX, 35, 35] == pytest.approx(0.0, abs=0.01)


def test_unknown_species_falls_back_to_the_default_crown() -> None:
    lookup = SpeciesCrownLookup(catalog(), SETTINGS)
    assert lookup.crown_for(TREE, "неизвестное дерево") == SETTINGS.default_tree_crown_m
    assert lookup.crown_for(SHRUB, "") == SETTINGS.default_shrub_crown_m


def test_species_name_matches_regardless_of_case_and_yo() -> None:
    lookup = SpeciesCrownLookup(catalog(), SETTINGS)
    assert lookup.crown_for(TREE, "ЛИПА МЕЛКОЛИСТНАЯ") == 8.0


def test_counts_split_by_target() -> None:
    plantings = [
        planting_at(1.0, 1.0, TREE, "Липа мелколистная"),
        planting_at(2.0, 2.0, SHRUB, "Кизильник блестящий"),
        planting_at(3.0, 3.0, SHRUB, "Кизильник блестящий"),
    ]
    assert planting_counts(plantings) == {TREE: 1, SHRUB: 2}
