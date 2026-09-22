from pathlib import Path

from shapely.geometry import LineString

from greenplan.domain.obstacle_kinds import BUILDING_WALL
from greenplan.domain.site import (
    BUILDINGS_NOT_FOUND,
    NETWORKS_NOT_FOUND,
    PROTECTED_AREAS_NOT_CHECKED,
    Obstacle,
)
from greenplan.knowledge.explanation_terms import ExplanationTerms
from greenplan.recognition.site_model_builder import site_warnings

from fixtures.norms_factory import network


def building() -> Obstacle:
    return Obstacle(BUILDING_WALL, LineString([(0, 0), (10, 0)]), "building", "tile_tp", ("layer:building",))


def gas_pipeline() -> Obstacle:
    return network("gas_pipeline", [(0, 0), (10, 0)])


def test_missing_buildings_are_reported() -> None:
    assert site_warnings((gas_pipeline(),)) == (BUILDINGS_NOT_FOUND, PROTECTED_AREAS_NOT_CHECKED)


def test_missing_underground_networks_are_reported() -> None:
    assert site_warnings((building(),))[0] == NETWORKS_NOT_FOUND


def test_complete_site_leaves_only_the_protected_area_note() -> None:
    assert site_warnings((building(), gas_pipeline())) == (PROTECTED_AREAS_NOT_CHECKED,)


def test_every_warning_has_a_russian_text(knowledge_root: Path) -> None:
    terms = ExplanationTerms.from_file(knowledge_root / "rules" / "explanation_terms.yaml")
    for code in (NETWORKS_NOT_FOUND, BUILDINGS_NOT_FOUND, PROTECTED_AREAS_NOT_CHECKED):
        text = terms.site_warning(code)
        assert text != code
        assert any("а" <= letter <= "я" for letter in text.lower())
