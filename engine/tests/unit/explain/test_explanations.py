from pathlib import Path

import pytest
from shapely.geometry import Point

from greenplan.domain.decisions import (
    REJECTED,
    TOO_CLOSE_TO_EXISTING_TREE,
    Clearance,
    PlantCandidate,
    PlantingDecision,
)
from greenplan.domain.norms import CONDITIONAL, GEOMETRY_MEASUREMENT, PROHIBITIVE, TREE, Requirement
from greenplan.domain.site import ExistingTree
from greenplan.explain.citation_policy import CitationPolicy
from greenplan.explain.explanation_builder import ExplanationBuilder
from greenplan.explain.number_format import format_number
from greenplan.knowledge.invasive_registry import ALLOWED, InvasiveVerdict
from greenplan.knowledge.norms_repository import NormsRepository
from greenplan.species.site_context import PlantingContext
from greenplan.species.species_selector import SpeciesAssignment
from greenplan.species.species_suitability import SelectionReason

from fixtures.explanation_checks import citations_violating_policy, unexplained_numbers
from fixtures.norms_factory import NormsToolkit, network, open_site, point_obstacle
from fixtures.species_factory import species


@pytest.fixture(scope="module")
def toolkit(knowledge_root: Path) -> NormsToolkit:
    return NormsToolkit(knowledge_root)


@pytest.fixture(scope="module")
def builder(knowledge_root: Path) -> ExplanationBuilder:
    return ExplanationBuilder.from_knowledge(knowledge_root)


@pytest.fixture(scope="module")
def policy(knowledge_root: Path) -> CitationPolicy:
    return CitationPolicy(NormsRepository.from_knowledge(knowledge_root).citations)


def tree_decision(toolkit: NormsToolkit, site, x: float, y: float, crown: float = 5.0) -> PlantingDecision:
    return toolkit.evaluator(site).evaluate(PlantCandidate("T-0001", Point(x, y), TREE, crown))


def gas_site(outer_radius_m: float | None = 0.055):
    return open_site((network("gas_pipeline", [(-50, 0), (50, 0)], outer_radius_m=outer_radius_m),))


def test_number_format_uses_decimal_comma_and_trims_zeros() -> None:
    assert [format_number(value) for value in (1.5, 2.0, 3.333, 0.004, -0.001)] == [
        "1,5",
        "2",
        "3,33",
        "0",
        "0",
    ]


def test_verified_citation_carries_locator(policy: CitationPolicy) -> None:
    view = policy.view("sp42_t9_1_gas_sewer")
    assert view.locator.startswith("таблица 9.1")
    assert view.text_ru.startswith("СП 42.13330.2016, таблица 9.1")


@pytest.mark.parametrize("key", ["pue", "ppm369_invasive", "sp396_1325800"])
def test_unverified_citation_has_no_locator(policy: CitationPolicy, key: str) -> None:
    view = policy.view(key)
    assert view.locator is None
    assert "," not in view.text_ru


def test_design_assumption_is_named_as_assumption(policy: CitationPolicy) -> None:
    assert policy.view("design_assumption").text_ru == "допущение"


def test_rejected_tree_explains_deficit_with_verified_reference(
    toolkit: NormsToolkit, builder: ExplanationBuilder
) -> None:
    explanation = builder.for_decision(tree_decision(toolkit, gas_site(), 0, 1.55))
    text = explanation.explanation_ru
    assert explanation.status == REJECTED
    assert text.startswith("Посадка дерева в данной точке отклонена.")
    assert "дефицит" in text
    assert "СП 42.13330.2016, таблица 9.1, строка «Подземные сети: газопровод, канализация»" in text
    assert explanation.clearances[0].rule_id == "sp42_gas_tree"


def test_conditional_tree_names_zone_and_condition(
    toolkit: NormsToolkit, builder: ExplanationBuilder
) -> None:
    text = builder.for_decision(tree_decision(toolkit, gas_site(), 0, 1.8)).explanation_ru
    assert text.startswith("Посадка дерева допустима условно.")
    assert "охранной зоне газораспределительной сети" in text
    assert "письменное разрешение эксплуатационной организации" in text


def test_crown_increment_is_explained_with_note_reference(
    toolkit: NormsToolkit, builder: ExplanationBuilder
) -> None:
    site = open_site((network("water_supply", [(-50, 0), (50, 0)], outer_radius_m=0.1),))
    text = builder.for_decision(tree_decision(toolkit, site, 0, 4.5, crown=9.0)).explanation_ru
    assert "увеличена на 2 м для кроны 9 м" in text
    assert "примечание 1 к таблице 9.1" in text


def test_assumed_network_radius_is_disclosed(toolkit: NormsToolkit, builder: ExplanationBuilder) -> None:
    text = builder.for_decision(tree_decision(toolkit, gas_site(None), 0, 3.0)).explanation_ru
    assert "не подписан" in text


def test_existing_tree_violation_is_marked_as_assumption(
    toolkit: NormsToolkit, builder: ExplanationBuilder
) -> None:
    site = open_site((), existing_trees=(ExistingTree(Point(0, 0), "keep", "dendro", "dendro"),))
    explanation = builder.for_decision(tree_decision(toolkit, site, 2, 0))
    assert explanation.violations[0].code == TOO_CLOSE_TO_EXISTING_TREE
    assert "(допущение)" in explanation.explanation_ru


def test_requirement_citing_unverified_document_is_rendered_without_locator(
    builder: ExplanationBuilder,
) -> None:
    obstacle = point_obstacle("overhead_line", 0, 0)
    requirement = Requirement(
        "pue_probe",
        "overhead_line",
        TREE,
        PROHIBITIVE,
        "distance",
        5.0,
        5.0,
        GEOMETRY_MEASUREMENT,
        ("pue",),
        (),
        0.0,
        "",
        False,
    )
    clearance = Clearance(obstacle, requirement, 3.0, False, False)
    decision = PlantingDecision(PlantCandidate("R-0001", Point(3, 0), TREE, 5.0), REJECTED, (clearance,), ())
    explanation = builder.for_decision(decision)
    assert "(ПУЭ)" in explanation.explanation_ru
    assert "расстояния от ВЛ до деревьев" not in explanation.explanation_ru
    assert citations_violating_policy(explanation) == []


def test_species_reasons_and_invasive_check_are_explained(
    toolkit: NormsToolkit, builder: ExplanationBuilder
) -> None:
    decision = tree_decision(toolkit, open_site(()), 0, 0)
    reason = SelectionReason(
        "context:bus_stop",
        "Деревья с компактной кроной, не ближе 2,0 м от боковых конструкций павильона.",
        "tsn_p4_10_4",
    )
    context = PlantingContext(20.0, float("inf"), 6.0, float("inf"), frozenset({"bus_stop"}))
    assignment = SpeciesAssignment(
        decision,
        species("rowan", name_ru="Рябина обыкновенная"),
        context,
        InvasiveVerdict(ALLOWED),
        (reason,),
    )
    text = builder.for_assignment(assignment).explanation_ru
    assert "Порода: Рябина обыкновенная." in text
    assert "623-ПП / МГСН 1.02-02, п. 4.10.4" in text
    assert "не входит в известные перечни инвазивных растений" in text


@pytest.mark.parametrize(
    ("site_factory", "x", "y", "crown"),
    [
        (lambda: gas_site(), 0, 1.55, 5.0),
        (lambda: gas_site(), 0, 1.8, 5.0),
        (lambda: gas_site(), 0, 2.5, 5.0),
        (lambda: gas_site(None), 0, 3.0, 5.0),
        (lambda: open_site((network("water_supply", [(-50, 0), (50, 0)], outer_radius_m=0.1),)), 0, 4.5, 9.0),
        (
            lambda: open_site((network("heating_network", [(-50, 0), (50, 0)], outer_radius_m=0.5),)),
            0,
            2.2,
            5.0,
        ),
        (lambda: open_site((point_obstacle("lighting_pole", 0, 0),)), 3.3, 0, 5.0),
        (
            lambda: open_site((), existing_trees=(ExistingTree(Point(0, 0), "keep", "dendro", "dendro"),)),
            2.7,
            0,
            5.0,
        ),
    ],
)
def test_every_number_in_text_exists_in_structure(toolkit, builder, site_factory, x, y, crown) -> None:
    explanation = builder.for_decision(tree_decision(toolkit, site_factory(), x, y, crown))
    assert unexplained_numbers(explanation) == set()
    assert citations_violating_policy(explanation) == []


def test_conditional_status_constant_matches_severity_name() -> None:
    assert CONDITIONAL == "conditional"


def test_repeated_violations_of_one_rule_are_reported_once_with_worst_margin(
    toolkit: NormsToolkit, builder: ExplanationBuilder
) -> None:
    site = open_site(
        (
            network("gas_pipeline", [(-50, 0), (50, 0)], outer_radius_m=0.055),
            network("gas_pipeline", [(-50, 0.6), (50, 0.6)], outer_radius_m=0.055),
        )
    )
    explanation = builder.for_decision(tree_decision(toolkit, site, 0, 1.5))
    gas_violations = [
        item for item in explanation.clearances if item.rule_id == "sp42_gas_tree" and not item.satisfied
    ]
    assert len(gas_violations) == 1
    assert gas_violations[0].actual_m == pytest.approx(0.9 - 0.055 - 0.05, abs=1e-3)
    assert explanation.explanation_ru.count("Нарушено") == 1
