from dataclasses import replace
from pathlib import Path

import pytest
from shapely.geometry import LineString, Point

from greenplan.domain.decisions import NO_SUITABLE_SPECIES, REJECTED, PlantCandidate, PlantingDecision
from greenplan.domain.norms import SHRUB, TREE
from greenplan.domain.obstacle_kinds import CARRIAGEWAY_EDGE
from greenplan.domain.site import Obstacle, SiteModel
from greenplan.knowledge.composition_roles import CompositionRoles, SpeciesRole
from greenplan.knowledge.invasive_registry import CONDITIONAL, InvasiveRegistry
from greenplan.knowledge.plant_catalog import NOT_STREET_SUITABLE, PlantCatalog, SelectionRule
from greenplan.species.site_context import (
    NEAR_HEATING_NETWORK,
    STREET_CARRIAGEWAY_ADJACENT,
    SiteContextDetector,
)
from greenplan.species.species_selector import SpeciesOutcome, SpeciesSelector
from greenplan.species.species_settings import SpeciesSettings
from greenplan.species.species_suitability import SpeciesSuitability

from fixtures.norms_factory import NormsToolkit, network, open_site
from fixtures.placement_factory import street_site
from fixtures.species_factory import catalog, species

DEFAULT_SETTINGS = SpeciesSettings()


@pytest.fixture(scope="module")
def toolkit(knowledge_root: Path) -> NormsToolkit:
    return NormsToolkit(knowledge_root)


@pytest.fixture(scope="module")
def registry(knowledge_root: Path) -> InvasiveRegistry:
    return InvasiveRegistry.from_file(knowledge_root / "plants" / "invasive_moscow.yaml")


def assign(
    toolkit: NormsToolkit,
    registry: InvasiveRegistry,
    site: SiteModel,
    plant_catalog: PlantCatalog,
    decisions: list[PlantingDecision],
    settings: SpeciesSettings = DEFAULT_SETTINGS,
) -> SpeciesOutcome:
    selector = SpeciesSelector(
        SpeciesSuitability(plant_catalog, registry, settings),
        toolkit.evaluator(site),
        SiteContextDetector(site, settings),
        settings,
    )
    return selector.assign(decisions)


def planned(toolkit: NormsToolkit, site: SiteModel, target: str, x: float, y: float) -> PlantingDecision:
    crown = 5.0 if target == TREE else 1.5
    return toolkit.evaluator(site).evaluate(PlantCandidate(f"{target}-{x}", Point(x, y), target, crown))


def carriageway_site() -> SiteModel:
    edge = Obstacle(
        CARRIAGEWAY_EDGE, LineString([(-50, 0), (50, 0)]), "surfaces", "surface_edges", ("surface",)
    )
    return open_site((edge,))


def test_context_detector_measures_distances_and_tags() -> None:
    context = SiteContextDetector(street_site(), DEFAULT_SETTINGS).detect(Point(50, 11))
    assert context.carriageway_distance_m == pytest.approx(3.0)
    assert context.heating_axis_distance_m == float("inf")
    assert context.tags == frozenset({STREET_CARRIAGEWAY_ADJACENT})


def test_heating_restricted_species_are_not_chosen_closer_than_their_minimum(
    toolkit: NormsToolkit, registry: InvasiveRegistry
) -> None:
    site = open_site((network("heating_network", [(-50, 0), (50, 0)], outer_radius_m=0.3),))
    plant_catalog = catalog(
        species("dogwood", "shrub", 2.0, 2.5, name_ru="Дёрен тестовый", heating_min_axis_m=4.0, usage=1000),
        species("spiraea", "shrub", 1.2, 1.5, usage=10),
    )
    near = planned(toolkit, site, SHRUB, 0, 3.0)
    far = planned(toolkit, site, SHRUB, 30, 5.0)
    outcome = assign(toolkit, registry, site, plant_catalog, [near, far])
    chosen = [assignment.species.key for assignment in outcome.assignments]
    assert chosen == ["spiraea", "dogwood"]
    assert NEAR_HEATING_NETWORK in outcome.assignments[0].context.tags


def test_conflicting_invasive_species_is_not_offered_by_default(
    toolkit: NormsToolkit, registry: InvasiveRegistry
) -> None:
    site = open_site(())
    plant_catalog = catalog(
        species("cornus_alba", "shrub", 2.0, 2.5, name_ru="Дёрен белый", latin="Cornus alba")
    )
    outcome = assign(toolkit, registry, site, plant_catalog, [planned(toolkit, site, SHRUB, 0, 0)])
    assert outcome.assignments == ()
    assert outcome.rejections[0].status == REJECTED
    assert outcome.rejections[0].site_violations[-1].code == NO_SUITABLE_SPECIES


def test_conflicting_invasive_species_can_be_offered_as_conditional(
    toolkit: NormsToolkit, registry: InvasiveRegistry
) -> None:
    site = open_site(())
    plant_catalog = catalog(
        species("cornus_alba", "shrub", 2.0, 2.5, name_ru="Дёрен белый", latin="Cornus alba")
    )
    settings = SpeciesSettings(allow_conditional_species=True)
    outcome = assign(toolkit, registry, site, plant_catalog, [planned(toolkit, site, SHRUB, 0, 0)], settings)
    assert outcome.assignments[0].invasive.status == CONDITIONAL


def test_wide_crown_that_breaks_clearance_gives_way_to_narrow_crown(
    toolkit: NormsToolkit, registry: InvasiveRegistry
) -> None:
    site = open_site((network("water_supply", [(-50, 0), (50, 0)], outer_radius_m=0.1),))
    plant_catalog = catalog(species("wide_tree", crown_diameter_m=10.0, usage=1000), species("narrow_tree"))
    assignment = assign(
        toolkit, registry, site, plant_catalog, [planned(toolkit, site, TREE, 0, 3.0)]
    ).assignments[0]
    assert assignment.species.key == "narrow_tree"
    assert assignment.decision.candidate.crown_diameter_m == 5.0
    assert assignment.decision.candidate.species_name_ru == "narrow_tree"
    assert assignment.decision.is_placeable


def test_trees_in_a_row_keep_the_species_of_their_neighbours(
    toolkit: NormsToolkit, registry: InvasiveRegistry
) -> None:
    site = open_site((network("water_supply", [(-5, 0), (5, 0)], outer_radius_m=0.1),))
    plant_catalog = catalog(species("wide_tree", crown_diameter_m=10.0, usage=1000), species("narrow_tree"))
    row = [planned(toolkit, site, TREE, x, 3.0) for x in (0, 6, 12, 18, 24)]
    grouped = assign(toolkit, registry, site, plant_catalog, row)
    ungrouped = assign(
        toolkit, registry, site, plant_catalog, row, SpeciesSettings(tree_grouping_distance_m=0.0)
    )
    assert [item.species.key for item in grouped.assignments] == ["narrow_tree"] * 5
    assert [item.species.key for item in ungrouped.assignments] == ["narrow_tree"] * 2 + ["wide_tree"] * 3


def test_street_context_prefers_rule_species_and_records_reason(
    toolkit: NormsToolkit, registry: InvasiveRegistry
) -> None:
    site = carriageway_site()
    rule = SelectionRule(
        "street_carriageway_adjacent", prefer=("rowan",), reason_ru="устойчивость к реагентам"
    )
    plant_catalog = catalog(species("linden", usage=1000), species("rowan"), rules=(rule,))
    assignment = assign(
        toolkit, registry, site, plant_catalog, [planned(toolkit, site, TREE, 0, 3.0)]
    ).assignments[0]
    assert assignment.species.key == "rowan"
    assert assignment.reasons[0].code == "context:street_carriageway_adjacent"


def test_separate_groups_rotate_between_similarly_ranked_species(
    toolkit: NormsToolkit, registry: InvasiveRegistry
) -> None:
    site = open_site(())
    plant_catalog = catalog(
        species("spiraea", "shrub", 1.2, 1.5, usage=100), species("hydrangea", "shrub", 1.5, 1.5, usage=50)
    )
    shrubs = [planned(toolkit, site, SHRUB, x, 0.0) for x in range(0, 100, 10)]
    diverse = assign(toolkit, registry, site, plant_catalog, shrubs)
    monotone = assign(toolkit, registry, site, plant_catalog, shrubs, SpeciesSettings(diversity_penalty=0.0))
    diverse_keys = [item.species.key for item in diverse.assignments]
    assert {"spiraea", "hydrangea"} == set(diverse_keys)
    assert abs(diverse_keys.count("spiraea") - diverse_keys.count("hydrangea")) <= 2
    assert {item.species.key for item in monotone.assignments} == {"spiraea"}


def test_species_unsuitable_for_streets_is_skipped_near_carriageway(
    toolkit: NormsToolkit, registry: InvasiveRegistry
) -> None:
    site = carriageway_site()
    plant_catalog = catalog(
        species("oak", usage=5000, street_suitability=NOT_STREET_SUITABLE), species("linden")
    )
    assignment = assign(
        toolkit, registry, site, plant_catalog, [planned(toolkit, site, TREE, 0, 3.0)]
    ).assignments[0]
    assert assignment.species.key == "linden"


def in_element(decision: PlantingDecision, element_id: str) -> PlantingDecision:
    return replace(decision, candidate=replace(decision.candidate, element_id=element_id))


def test_every_member_of_a_composition_element_gets_the_same_species(
    toolkit: NormsToolkit, registry: InvasiveRegistry
) -> None:
    site = open_site(())
    plant_catalog = catalog(
        species("spiraea", "shrub", 1.2, 1.5, usage=100), species("hydrangea", "shrub", 1.5, 1.5, usage=50)
    )
    hedge = [in_element(planned(toolkit, site, SHRUB, x, 0.0), "hedge-1") for x in range(0, 30, 3)]
    group = [in_element(planned(toolkit, site, SHRUB, x, 20.0), "group-1") for x in range(0, 30, 3)]
    outcome = assign(toolkit, registry, site, plant_catalog, [*hedge, *group])
    by_element: dict[str, set[str]] = {}
    for item in outcome.assignments:
        by_element.setdefault(item.decision.candidate.element_id, set()).add(item.species.key)
    assert all(len(keys) == 1 for keys in by_element.values())
    assert by_element["hedge-1"] != by_element["group-1"]


def test_palette_limit_reuses_species_already_on_the_site(
    toolkit: NormsToolkit, registry: InvasiveRegistry
) -> None:
    site = open_site(())
    plant_catalog = catalog(
        species("spiraea", "shrub", 1.2, 1.5, usage=100),
        species("hydrangea", "shrub", 1.5, 1.5, usage=90),
        species("cornus", "shrub", 1.5, 1.5, usage=80),
    )
    shrubs = [in_element(planned(toolkit, site, SHRUB, x, 0.0), f"group-{x}") for x in range(0, 60, 10)]
    limited = assign(toolkit, registry, site, plant_catalog, shrubs, SpeciesSettings(shrub_palette_size=2))
    assert len({item.species.key for item in limited.assignments}) == 2


def test_hedge_element_prefers_a_species_suited_for_hedges(
    toolkit: NormsToolkit, registry: InvasiveRegistry
) -> None:
    site = open_site(())
    plant_catalog = catalog(
        species("spiraea", "shrub", 1.2, 1.5, usage=100), species("cotoneaster", "shrub", 1.2, 1.5, usage=10)
    )
    roles = CompositionRoles({"hedge": SpeciesRole(frozenset({"cotoneaster"}), "хорошо формуется")})
    selector = SpeciesSelector(
        SpeciesSuitability(plant_catalog, registry, DEFAULT_SETTINGS),
        toolkit.evaluator(site),
        SiteContextDetector(site, DEFAULT_SETTINGS),
        DEFAULT_SETTINGS,
        roles=roles,
    )
    hedge = [in_element(planned(toolkit, site, SHRUB, x, 0.0), "hedge-1") for x in range(0, 12, 2)]
    outcome = selector.assign(hedge, {"hedge-1": "hedge"})
    assert {item.species.key for item in outcome.assignments} == {"cotoneaster"}
    assert any(reason.reason_ru == "хорошо формуется" for reason in outcome.assignments[0].reasons)
