from pathlib import Path

import pytest
from shapely.geometry import Point, Polygon

from greenplan.domain.decisions import (
    ACCEPTED,
    CONDITIONALLY_ACCEPTED,
    OUTSIDE_PLANTABLE_SURFACE,
    REJECTED,
    TOO_CLOSE_TO_EXISTING_TREE,
    PlantCandidate,
)
from greenplan.domain.norms import SHRUB, TREE
from greenplan.domain.site import ExistingTree

from fixtures.norms_factory import NormsToolkit, network, open_site, point_obstacle


@pytest.fixture(scope="module")
def toolkit(knowledge_root: Path) -> NormsToolkit:
    return NormsToolkit(knowledge_root)


def tree_at(x: float, y: float, crown_diameter_m: float = 5.0, species: str | None = None) -> PlantCandidate:
    return PlantCandidate("T-1", Point(x, y), TREE, crown_diameter_m, None, species)


def gas_site():
    return open_site((network("gas_pipeline", [(-50, 0), (50, 0)], outer_radius_m=0.055),))


def test_tree_too_close_to_gas_pipeline_surface_is_rejected(toolkit: NormsToolkit) -> None:
    decision = toolkit.evaluator(gas_site()).evaluate(tree_at(0, 1.55))
    assert decision.status == REJECTED
    blocking = decision.blocking_clearances[0]
    assert blocking.requirement.rule_id == "sp42_gas_tree"
    assert blocking.actual_m == pytest.approx(1.55 - 0.055 - 0.05)


def test_tree_outside_table_distance_but_inside_gas_zone_is_conditional(toolkit: NormsToolkit) -> None:
    decision = toolkit.evaluator(gas_site()).evaluate(tree_at(0, 1.8))
    assert decision.status == CONDITIONALLY_ACCEPTED
    assert decision.condition_clearances[0].requirement.rule_id == "pp878_zone"


def test_tree_outside_zone_is_accepted_with_reported_clearances(toolkit: NormsToolkit) -> None:
    decision = toolkit.evaluator(gas_site()).evaluate(tree_at(0, 2.5))
    assert decision.status == ACCEPTED
    assert {clearance.requirement.rule_id for clearance in decision.clearances} >= {
        "sp42_gas_tree",
        "pp878_zone",
    }


def test_shrub_near_sewer_is_not_blocked_by_unregulated_table_cell(toolkit: NormsToolkit) -> None:
    site = open_site((network("sewer", [(-50, 0), (50, 0)], outer_radius_m=0.15),))
    shrub = PlantCandidate("S-1", Point(0, 0.5), SHRUB, 1.5)
    assert toolkit.evaluator(site).evaluate(shrub).status == ACCEPTED


def test_lighting_pole_distance_is_measured_to_trunk_axis(toolkit: NormsToolkit) -> None:
    site = open_site((point_obstacle("lighting_pole", 0, 0),))
    assert toolkit.evaluator(site).evaluate(tree_at(3.9, 0)).status == REJECTED
    assert toolkit.evaluator(site).evaluate(tree_at(4.1, 0)).status == ACCEPTED


def test_point_outside_plantable_surface_is_rejected_with_site_violation(toolkit: NormsToolkit) -> None:
    lawn = Polygon([(10, 10), (20, 10), (20, 20), (10, 20)])
    site = open_site((), plantable=lawn)
    decision = toolkit.evaluator(site).evaluate(tree_at(0, 0))
    assert decision.status == REJECTED
    assert decision.site_violations[0].code == OUTSIDE_PLANTABLE_SURFACE


def test_tree_near_kept_existing_tree_is_rejected(toolkit: NormsToolkit) -> None:
    existing = (
        ExistingTree(Point(0, 0), "keep", "tp", "tp"),
        ExistingTree(Point(1, 0), "remove", "dp", "dp"),
    )
    site = open_site((), existing_trees=existing)
    near_kept = toolkit.evaluator(site).evaluate(tree_at(2, 0))
    near_removed_only = toolkit.evaluator(open_site((), existing_trees=existing[1:])).evaluate(tree_at(2, 0))
    assert near_kept.site_violations[0].code == TOO_CLOSE_TO_EXISTING_TREE
    assert near_removed_only.status == ACCEPTED


def test_large_crown_makes_previously_valid_point_invalid(toolkit: NormsToolkit) -> None:
    site = open_site((network("water_supply", [(-50, 0), (50, 0)], outer_radius_m=0.1),))
    assert toolkit.evaluator(site).evaluate(tree_at(0, 2.5, crown_diameter_m=5.0)).status == ACCEPTED
    assert toolkit.evaluator(site).evaluate(tree_at(0, 2.5, crown_diameter_m=9.0)).status == REJECTED


def test_advisory_heating_species_rule_does_not_reject(toolkit: NormsToolkit) -> None:
    site = open_site((network("heating_network", [(-50, 0), (50, 0)], outer_radius_m=0.5),))
    decision = toolkit.evaluator(site).evaluate(tree_at(0, 3.7, species="Липа мелколистная"))
    assert decision.status == ACCEPTED
    assert not decision.advisory_clearances
    decision_near = toolkit.evaluator(site).evaluate(
        PlantCandidate("S-1", Point(0, 3.7), SHRUB, 2.0, None, "Дёрен белый")
    )
    assert decision_near.status == ACCEPTED
    assert decision_near.advisory_clearances[0].requirement.rule_id == "tsn_heating_species_3_4m"
