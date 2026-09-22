from pathlib import Path

import pytest

from greenplan.knowledge.citations_repository import CitationsRepository
from greenplan.knowledge.plant_catalog import PlantCatalog
from greenplan.knowledge.territory_catalog import TerritoryCatalog
from greenplan.knowledge.yaml_loader import load_yaml_mapping
from greenplan.species.selection_texts import SelectionTexts

TRAIT_LEVELS = {"high", "medium", "low"}
MOISTURE_LEVELS = {"dry", "moderate", "moist"}
SHADE_LEVELS = {"tolerant", "medium", "intolerant"}


@pytest.fixture(scope="module")
def citations(knowledge_root: Path) -> CitationsRepository:
    return CitationsRepository.from_file(knowledge_root / "rules" / "citations.yaml")


@pytest.fixture(scope="module")
def plant_catalog(knowledge_root: Path) -> PlantCatalog:
    return PlantCatalog.from_file(knowledge_root / "plants" / "assortment.yaml")


def test_selection_reason_sources_exist(knowledge_root: Path, citations: CitationsRepository) -> None:
    texts = SelectionTexts.from_knowledge(knowledge_root)
    missing = sorted(key for key in texts.source_refs() if not citations.contains(key))
    assert missing == []


def test_every_mapped_species_is_present_in_the_territory_table(
    knowledge_root: Path, plant_catalog: PlantCatalog
) -> None:
    territories = TerritoryCatalog.from_knowledge(knowledge_root)
    column = territories.category(None).tsn_column
    missing = sorted(
        species.territory_table_name
        for species in plant_catalog.species()
        if species.territory_table_name and territories.verdict(species.territory_table_name, column) is None
    )
    assert missing == []


def test_species_traits_use_known_levels(plant_catalog: PlantCatalog) -> None:
    for species in plant_catalog.species():
        traits = species.traits
        assert traits is not None, species.key
        assert traits.gas_tolerance in TRAIT_LEVELS
        assert traits.salt_tolerance in TRAIT_LEVELS
        assert traits.dust_capture in TRAIT_LEVELS
        assert traits.moisture in MOISTURE_LEVELS
        assert traits.shade_tolerance in SHADE_LEVELS


def test_noise_barrier_species_follow_the_verified_note(plant_catalog: PlantCatalog) -> None:
    marked = {species.name_ru for species in plant_catalog.species() if species.noise_barrier}
    assert marked
    assert all(
        name.startswith(("Липа мелколистная", "Клён остролистный", "Пузыреплодник", "Дёрен белый"))
        for name in marked
    )


def test_every_territory_category_has_a_composition_note(knowledge_root: Path) -> None:
    territories = TerritoryCatalog.from_knowledge(knowledge_root)
    assert len(territories.categories()) >= 10
    assert all(category.composition_ru for category in territories.categories())


def test_territory_table_keeps_the_source_reference(knowledge_root: Path) -> None:
    table = load_yaml_mapping(knowledge_root / "plants" / "territory_suitability.yaml")
    assert table["meta"]["source_ref"] == "tsn_tV6"
    assert len(table["species"]) > 70
