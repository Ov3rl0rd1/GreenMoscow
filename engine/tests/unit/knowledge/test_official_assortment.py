from pathlib import Path

import pytest

from greenplan.domain.errors import KnowledgeValidationError
from greenplan.domain.norms import TREE
from greenplan.knowledge.official_assortment import (
    ADDITIONAL,
    MAIN,
    PERSPECTIVE,
    ROAD_SENSITIVE_NOTE,
    SPREAD_CONTROL_NOTE,
    OfficialAssortment,
)
from greenplan.knowledge.plant_catalog import PlantCatalog
from greenplan.knowledge.territory_catalog import TerritoryCatalog

WHITE_DOGWOOD = "Дерен белый/сибирский (формы и сорта)"
NORWAY_SPRUCE = "Ель обыкновенная/европейская (формы и сорта)"
ARNOLD_HAWTHORN = "Боярышник Арнольда"


@pytest.fixture(scope="module")
def official(knowledge_root: Path) -> OfficialAssortment:
    return OfficialAssortment.from_knowledge(knowledge_root)


def test_all_three_levels_and_seven_notes_are_loaded(official: OfficialAssortment) -> None:
    assert len(official) == 329
    assert {official.note_ru(number)[:9] for number in range(1, 8)}
    assert "369-ПП" in official.note_ru(SPREAD_CONTROL_NOTE)


def test_white_dogwood_is_main_assortment_with_spread_control(official: OfficialAssortment) -> None:
    (entry,) = official.entries([WHITE_DOGWOOD], is_tree=False)
    assert entry.level == MAIN
    assert entry.has_note(SPREAD_CONTROL_NOTE)
    assert entry.allows(["roads"])
    assert not entry.allows(["preschool"])


def test_norway_spruce_is_road_sensitive_and_not_for_roads(official: OfficialAssortment) -> None:
    (entry,) = official.entries([NORWAY_SPRUCE], is_tree=True)
    assert entry.has_note(ROAD_SENSITIVE_NOTE)
    assert not entry.allows(["roads"])
    assert entry.allows(["yards", "parks"])


def test_same_name_is_resolved_by_life_form(official: OfficialAssortment) -> None:
    (tree,) = official.entries([ARNOLD_HAWTHORN], is_tree=True)
    (shrub,) = official.entries([ARNOLD_HAWTHORN], is_tree=False)
    assert tree.allows(["roads"])
    assert not shrub.allows(["roads"])


def test_levels_are_ordered_main_additional_perspective(official: OfficialAssortment) -> None:
    ranks = {
        entry.level: entry.level_rank
        for name in ("Туя западная (формы и сорта)", WHITE_DOGWOOD, "Чубушник Гордона")
        for entry in official.entries([name], is_tree=False)
    }
    assert ranks[MAIN] < ranks[ADDITIONAL] < ranks[PERSPECTIVE]


def test_unknown_name_is_refused(official: OfficialAssortment) -> None:
    with pytest.raises(KnowledgeValidationError):
        official.entries(["Пальма кокосовая"], is_tree=True)


def test_every_catalog_species_resolves_its_official_names(
    official: OfficialAssortment, knowledge_root: Path
) -> None:
    catalog = PlantCatalog.from_file(knowledge_root / "plants" / "assortment.yaml")
    unmapped = []
    for species in catalog.species():
        entries = official.entries(species.official_names, species.target == TREE)
        if not entries:
            unmapped.append(species.key)
    assert sorted(unmapped) == ["aesculus_hippocastanum", "ulmus_parvifolia"]


def test_every_territory_category_uses_existing_official_columns(
    official: OfficialAssortment, knowledge_root: Path
) -> None:
    columns = set(official.column_ids())
    for category in TerritoryCatalog.from_knowledge(knowledge_root).categories():
        assert category.official_columns
        assert set(category.official_columns) <= columns
