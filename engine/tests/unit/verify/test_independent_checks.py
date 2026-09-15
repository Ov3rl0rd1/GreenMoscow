from pathlib import Path

import pytest
from shapely.geometry import Point

from greenplan.constraints.design_constraints import DesignConstraints
from greenplan.domain.decisions import ACCEPTED, CONDITIONALLY_ACCEPTED, TOO_CLOSE_TO_EXISTING_TREE
from greenplan.domain.norms import SHRUB, TREE
from greenplan.domain.site import ExistingTree
from greenplan.knowledge.norms_repository import NormsRepository
from greenplan.verify.independent_norm_checker import IndependentNormChecker
from greenplan.verify.site_placement_checker import SitePlacementChecker
from greenplan.verify.verification_model import CONDITION_NOT_DECLARED, SPACING_VIOLATED, PlacedPlant

from fixtures.norms_factory import network, open_site, point_obstacle


@pytest.fixture(scope="module")
def checker(knowledge_root: Path) -> IndependentNormChecker:
    return IndependentNormChecker(NormsRepository.from_knowledge(knowledge_root), 10.0, 0.001, 3.0)


def plant(
    identifier: str, x: float, y: float, plant_type: str = TREE, crown: float = 5.0, status: str = ACCEPTED
):
    return PlacedPlant(identifier, plant_type, "", status, Point(x, y), crown, "AI_PL_TREES_X", identifier)


def gas_site():
    return open_site((network("gas_pipeline", [(-50, 0), (50, 0)], outer_radius_m=0.055),))


def test_gas_table_distance_is_measured_between_surfaces(checker: IndependentNormChecker) -> None:
    violations = checker.violations([plant("T-1", 0, 1.55, status=CONDITIONALLY_ACCEPTED)], gas_site())
    assert [(item.code, item.actual_m, item.required_m) for item in violations] == [
        ("sp42_gas_tree", 1.445, 1.5)
    ]


def test_declared_conditional_plant_inside_zone_is_not_a_violation(checker: IndependentNormChecker) -> None:
    assert checker.violations([plant("T-1", 0, 1.8, status=CONDITIONALLY_ACCEPTED)], gas_site()) == []


def test_undeclared_condition_is_reported(checker: IndependentNormChecker) -> None:
    violations = checker.violations([plant("T-1", 0, 1.8)], gas_site())
    assert [item.code for item in violations] == [CONDITION_NOT_DECLARED]


def test_wide_crown_increases_required_distance(checker: IndependentNormChecker) -> None:
    site = open_site((network("water_supply", [(-50, 0), (50, 0)], outer_radius_m=0.1),))
    assert checker.violations([plant("T-1", 0, 2.5, crown=5.0)], site) == []
    assert [item.required_m for item in checker.violations([plant("T-2", 0, 2.5, crown=9.0)], site)] == [4.0]


def test_unregulated_shrub_distance_is_not_checked(checker: IndependentNormChecker) -> None:
    site = open_site((network("sewer", [(-50, 0), (50, 0)], outer_radius_m=0.15),))
    assert checker.violations([plant("S-1", 0, 0.5, plant_type=SHRUB, crown=1.5)], site) == []


def test_pole_distance_is_measured_to_trunk_axis(checker: IndependentNormChecker) -> None:
    site = open_site((point_obstacle("lighting_pole", 0, 0),))
    assert [item.actual_m for item in checker.violations([plant("T-1", 3.9, 0)], site)] == [3.9]


def site_checker() -> SitePlacementChecker:
    return SitePlacementChecker(DesignConstraints(), 6.0, 1.0, 1.5, 0.001)


def test_spacing_between_trees_is_reported_once_per_pair() -> None:
    violations = site_checker().violations(
        [plant("T-1", 0, 0), plant("T-2", 5, 0), plant("T-3", 20, 0)], open_site(())
    )
    assert [(item.plant_id, item.code) for item in violations] == [("T-2", SPACING_VIOLATED)]


def test_existing_tree_and_shrub_to_tree_distances_are_checked() -> None:
    site = open_site((), existing_trees=(ExistingTree(Point(0, 0), "keep", "dendro", "dendro"),))
    plants = [plant("T-1", 3, 0), plant("S-1", 3, 1.0, plant_type=SHRUB, crown=1.5)]
    codes = {(item.plant_id, item.code) for item in site_checker().violations(plants, site)}
    assert ("T-1", TOO_CLOSE_TO_EXISTING_TREE) in codes
    assert ("S-1", "too_close_to_planned_plant") in codes


def test_rounding_of_exported_coordinates_is_tolerated() -> None:
    violations = site_checker().violations([plant("T-1", 0, 0), plant("T-2", 5.9995, 0)], open_site(()))
    assert violations == []
