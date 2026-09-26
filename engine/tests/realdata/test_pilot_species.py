import pytest

from greenplan.knowledge.invasive_registry import ALLOWED, ALLOWED_WITH_CONTROL
from greenplan.placement.planting_plan import PlantingPlan
from greenplan.species.species_selector import SpeciesOutcome

pytestmark = [pytest.mark.realdata, pytest.mark.converter, pytest.mark.slow]


def test_most_planned_plants_receive_species(
    bagritskogo_species: SpeciesOutcome, bagritskogo_plan: PlantingPlan
) -> None:
    planned = len(bagritskogo_plan.trees) + len(bagritskogo_plan.shrubs)
    assert len(bagritskogo_species.assignments) + len(bagritskogo_species.rejections) == planned
    assert len(bagritskogo_species.assignments) >= 0.8 * planned


def test_assigned_species_respect_heating_minimum_invasive_policy_and_norms(
    bagritskogo_species: SpeciesOutcome,
) -> None:
    for assignment in bagritskogo_species.assignments:
        minimum = assignment.species.heating_min_axis_m
        assert assignment.invasive.status in {ALLOWED, ALLOWED_WITH_CONTROL}
        assert minimum is None or assignment.context.heating_axis_distance_m >= minimum
        assert assignment.decision.is_placeable
        assert assignment.decision.candidate.species_key == assignment.species.key
