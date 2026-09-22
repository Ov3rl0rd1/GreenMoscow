from dataclasses import replace
from pathlib import Path

import pytest
from shapely.geometry import LineString, Point, box

from greenplan.constraints.design_constraints import DesignConstraints
from greenplan.constraints.zone_builder import ZoneBuilder
from greenplan.domain.norms import TREE
from greenplan.domain.obstacle_kinds import CARRIAGEWAY_EDGE
from greenplan.placement.placement_settings import PlacementSettings
from greenplan.placement.planting_limits import PER_HECTARE, PER_KILOMETER, PlantingLimitsResolver
from greenplan.placement.planting_profile import PlantingProfile
from greenplan.placement.planting_zones import PlantingZoneBuilder
from greenplan.placement.score_maps import RuleScoreMap
from greenplan.placement.site_rasterizer import SiteRasterizer

from fixtures.norms_factory import NormsToolkit
from fixtures.placement_factory import street_site


@pytest.fixture(scope="module")
def toolkit(knowledge_root: Path) -> NormsToolkit:
    return NormsToolkit(knowledge_root)


@pytest.fixture(scope="module")
def table_toolkit(knowledge_root: Path) -> NormsToolkit:
    return NormsToolkit(knowledge_root, DesignConstraints(allow_root_barriers=False))


@pytest.fixture(scope="module")
def zone_toolkit(knowledge_root: Path) -> NormsToolkit:
    return NormsToolkit(
        knowledge_root, DesignConstraints(apply_protection_zones=True, allow_root_barriers=False)
    )


def tree_profile() -> PlantingProfile:
    settings = PlacementSettings()
    return PlantingProfile(
        TREE, 5.0, 6.0, None, CARRIAGEWAY_EDGE, RuleScoreMap(settings.tree_score), True, 0.0
    )


def zone_builder(toolkit: NormsToolkit) -> PlantingZoneBuilder:
    return PlantingZoneBuilder(ZoneBuilder(toolkit.resolver, toolkit.meter), toolkit.resolver, toolkit.design)


def test_prohibited_zone_contains_gas_band_pole_and_kept_tree(zone_toolkit: NormsToolkit) -> None:
    zones = zone_builder(zone_toolkit).build(street_site(), tree_profile(), ())
    assert zones.prohibited.contains(Point(50, 15))
    assert zones.prohibited.contains(Point(50, 16.5))
    assert not zones.prohibited.contains(Point(50, 16.7))
    assert zones.prohibited.contains(Point(30, 12.5))
    assert zones.prohibited.contains(Point(70, 15.5))
    assert zones.conditional.contains(Point(50, 16.8))


def test_planned_positions_are_excluded_with_profile_clearance(toolkit: NormsToolkit) -> None:
    profile = PlantingProfile(TREE, 5.0, 6.0, None, CARRIAGEWAY_EDGE, None, True, 1.5)
    zones = zone_builder(toolkit).build(street_site(), profile, (Point(50, 11),))
    assert zones.prohibited.contains(Point(51.4, 11))
    assert not zones.prohibited.contains(Point(51.6, 11))


def test_rasterizer_marks_allowed_conditional_clearance_and_edge_distance(zone_toolkit: NormsToolkit) -> None:
    site = street_site()
    zones = zone_builder(zone_toolkit).build(site, tree_profile(), ())
    raster = SiteRasterizer(0.5).rasterize(site, zones, CARRIAGEWAY_EDGE)
    grid = raster.grid
    assert raster.plantable.sum() * 0.25 == pytest.approx(1000.0)
    assert not raster.allowed[grid.cell_of(50.1, 15.1)]
    assert raster.allowed[grid.cell_of(50.1, 11.6)]
    assert raster.conditional[grid.cell_of(50.1, 13.1)]
    assert raster.clearance_m[grid.cell_of(50.1, 11.6)] == pytest.approx(2.0, abs=0.01)
    assert raster.reference_edge_distance_m[grid.cell_of(50.1, 11.1)] == pytest.approx(3.25, abs=0.01)


def test_street_limits_come_from_norms(toolkit: NormsToolkit) -> None:
    limits = PlantingLimitsResolver(toolkit.repository, PlacementSettings()).resolve(street_site())
    assert limits.tree_spacing_m == pytest.approx(6.0)
    assert limits.shrub_spacing_m == pytest.approx(1.0)
    assert limits.density_unit == PER_KILOMETER
    assert (limits.max_trees, limits.max_shrubs) == (18, 72)


def test_street_length_falls_back_to_boundary_rectangle(toolkit: NormsToolkit) -> None:
    limits = PlantingLimitsResolver(toolkit.repository, PlacementSettings()).resolve(street_site(False))
    assert limits.density_measure == pytest.approx(0.1)


def test_street_axes_outside_the_site_do_not_raise_the_density_cap(toolkit: NormsToolkit) -> None:
    site = street_site()
    extended = replace(
        site,
        street_axes=(LineString([(-900, 4), (1100, 4)]), LineString([(0, 500), (100, 500)])),
    )
    limits = PlantingLimitsResolver(toolkit.repository, PlacementSettings()).resolve(extended)
    assert limits.density_measure == pytest.approx(0.1)


def test_distant_boundary_pieces_are_measured_separately(toolkit: NormsToolkit) -> None:
    site = street_site(False)
    split = replace(site, boundary=site.boundary.union(box(4600, 0, 4650, 20)))
    limits = PlantingLimitsResolver(toolkit.repository, PlacementSettings()).resolve(split)
    assert limits.density_measure == pytest.approx(0.15)


def test_strips_on_both_sides_of_a_street_count_as_one_street(toolkit: NormsToolkit) -> None:
    site = street_site(False)
    both_sides = replace(site, boundary=box(0, -2, 100, 10).union(box(0, 30, 100, 42)))
    limits = PlantingLimitsResolver(toolkit.repository, PlacementSettings()).resolve(both_sides)
    assert limits.density_measure == pytest.approx(0.1)


def test_non_street_context_is_limited_per_hectare_of_lawn(toolkit: NormsToolkit) -> None:
    settings = PlacementSettings(density_context="squares")
    limits = PlantingLimitsResolver(toolkit.repository, settings).resolve(street_site())
    assert limits.density_unit == PER_HECTARE
    assert limits.max_trees == 13
