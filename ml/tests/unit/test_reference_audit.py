from pathlib import Path

from shapely.geometry import LineString, Point, box

from greenplan.domain.norms import TREE
from greenplan.domain.obstacle_kinds import GAS_PIPELINE
from greenplan.domain.site import Obstacle, SiteDiagnostics, SiteModel
from greenplan.knowledge.norms_repository import NormsRepository
from greenplan.knowledge.pilot_objects import PilotObject
from greenplan.verify.independent_norm_checker import IndependentNormChecker
from greenplan_ml.reference_audit import ObjectAudit, ReferenceAuditor, render_audit_markdown
from greenplan_ml.reference_extractor import ReferencePlanting
from greenplan_ml.targets import SpeciesCrownLookup

OBJECT = PilotObject("demo", "Демо", "A", "pl_prefix", "Демо/вход.dwg", "Демо/проект.dwg")


def gas_site() -> SiteModel:
    gas = Obstacle(GAS_PIPELINE, LineString([(-50, 0), (50, 0)]), "Газопровод", "tile_up", ("layer",), 0.055)
    lawn = box(-50, -20, 50, 20)
    return SiteModel(lawn, lawn, (gas,), (), (), SiteDiagnostics())


def planting(x: float, y: float) -> ReferencePlanting:
    return ReferencePlanting(Point(x, y), TREE, "tree", "Липа мелколистная", "PL_TREES_Липа", "pl_prefix")


def auditor(knowledge_root: Path) -> ReferenceAuditor:
    repository = NormsRepository.from_knowledge(knowledge_root)
    return ReferenceAuditor(
        loader=None,
        extractor=None,
        checker=IndependentNormChecker(repository, 10.0, 0.001, 3.0),
        crowns=SpeciesCrownLookup.from_knowledge(knowledge_root),
    )


def test_reference_planting_on_the_pipe_is_reported(knowledge_root: Path) -> None:
    audit = auditor(knowledge_root)._audit_plantings(OBJECT, gas_site(), [planting(0.0, 0.3)])
    assert audit.checked
    assert audit.plantings == 1
    assert audit.violating_plants == 1
    assert audit.violation_share == 1.0
    assert audit.by_rule[0][0].startswith("sp42_gas_tree")


def test_planting_far_from_networks_passes(knowledge_root: Path) -> None:
    audit = auditor(knowledge_root)._audit_plantings(OBJECT, gas_site(), [planting(0.0, 15.0)])
    assert audit.violations == 0
    assert audit.violation_share == 0.0


def test_plantings_outside_the_lawn_are_counted(knowledge_root: Path) -> None:
    audit = auditor(knowledge_root)._audit_plantings(
        OBJECT, gas_site(), [planting(0.0, 15.0), planting(300.0, 300.0)]
    )
    assert audit.outside_plantable == 1
    assert audit.plantings == 2


def test_markdown_lists_objects_and_top_rules() -> None:
    audits = [
        ObjectAudit(
            "first",
            "A",
            True,
            plantings=10,
            violations=4,
            violating_plants=3,
            by_rule=(("sp42_gas_tree", 4),),
        ),
        ObjectAudit("second", "B", False, reason="в проектном решении нет посадок"),
    ]
    text = render_audit_markdown(audits)
    assert "first" in text and "30%" in text
    assert "sp42_gas_tree — 4" in text
    assert "в проектном решении нет посадок" in text
