from pathlib import Path

import pytest
from shapely.geometry import LineString, Point

from greenplan.domain.decisions import PlantCandidate
from greenplan.domain.errors import ConfigurationError
from greenplan.domain.norms import SHRUB, TREE
from greenplan.domain.obstacle_kinds import CARRIAGEWAY_EDGE
from greenplan.domain.site import Obstacle, SiteModel
from greenplan.knowledge.invasive_registry import ALLOWED_WITH_CONTROL, InvasiveRegistry
from greenplan.knowledge.official_assortment import OfficialAssortment
from greenplan.knowledge.plant_catalog import PlantCatalog
from greenplan.knowledge.territory_catalog import TerritoryCatalog
from greenplan.species.selection_texts import SelectionTexts
from greenplan.species.site_context import SiteContextDetector
from greenplan.species.species_selector import SpeciesSelector
from greenplan.species.species_settings import SpeciesSettings
from greenplan.species.species_suitability import SpeciesSuitability
from greenplan.species.territory_policy import FORBIDDEN, RECOMMENDED, TerritoryPolicy

from fixtures.norms_factory import NormsToolkit, open_site

SETTINGS = SpeciesSettings()
STREET_COLUMN = "streets_roads"
KNOWLEDGE_ROOT = Path(__file__).resolve().parents[4] / "knowledge"
OFFICIAL = OfficialAssortment.from_knowledge(KNOWLEDGE_ROOT)


@pytest.fixture(scope="module")
def territories(knowledge_root: Path) -> TerritoryCatalog:
    return TerritoryCatalog.from_knowledge(knowledge_root)


@pytest.fixture(scope="module")
def texts(knowledge_root: Path) -> SelectionTexts:
    return SelectionTexts.from_knowledge(knowledge_root)


@pytest.fixture(scope="module")
def plant_catalog(knowledge_root: Path) -> PlantCatalog:
    return PlantCatalog.from_file(knowledge_root / "plants" / "assortment.yaml")


@pytest.fixture(scope="module")
def registry(knowledge_root: Path) -> InvasiveRegistry:
    return InvasiveRegistry.from_file(knowledge_root / "plants" / "invasive_moscow.yaml")


@pytest.fixture(scope="module")
def toolkit(knowledge_root: Path) -> NormsToolkit:
    return NormsToolkit(knowledge_root)


def carriageway_site() -> SiteModel:
    edge = Obstacle(
        CARRIAGEWAY_EDGE, LineString([(-50, 0), (50, 0)]), "surfaces", "surface_edges", ("surface",)
    )
    return open_site((edge,))


def suitability(
    plant_catalog: PlantCatalog,
    registry: InvasiveRegistry,
    territories: TerritoryCatalog,
    texts: SelectionTexts,
    category_id: str,
) -> SpeciesSuitability:
    return SpeciesSuitability(
        plant_catalog, registry, SETTINGS, policy_for(territories, texts, category_id), texts
    )


def policy_for(territories: TerritoryCatalog, texts: SelectionTexts, category_id: str) -> TerritoryPolicy:
    return TerritoryPolicy(territories, territories.category(category_id), texts, OFFICIAL)


def ranked_keys(items) -> set[str]:
    return {item.species.key for item in items}


def test_default_category_is_a_district_street(territories: TerritoryCatalog) -> None:
    assert territories.category(None).category_id == "district_street"
    assert territories.category(None).tsn_column == STREET_COLUMN


def test_unknown_category_is_refused_with_the_known_list(territories: TerritoryCatalog) -> None:
    with pytest.raises(ConfigurationError, match="district_street"):
        territories.category("подъезд")


def test_table_verdicts_follow_the_source(territories: TerritoryCatalog) -> None:
    assert not territories.verdict("Ель колючая", STREET_COLUMN).allowed
    assert territories.verdict("Липа мелколистная", STREET_COLUMN).limited
    assert territories.verdict("Кизильник блестящий", STREET_COLUMN).allowed
    assert not territories.verdict("Кизильник блестящий", STREET_COLUMN).limited
    assert territories.verdict("Вид которого нет", STREET_COLUMN) is None


def test_official_table_decides_before_the_tsn_table(
    territories: TerritoryCatalog, texts: SelectionTexts, plant_catalog: PlantCatalog
) -> None:
    policy = policy_for(territories, texts, "district_street")
    assert policy.assess(plant_catalog.get("tilia_cordata")).kind == "official_main"
    assert policy.assess(plant_catalog.get("thuja_occidentalis")).kind == FORBIDDEN
    assert policy.assess(plant_catalog.get("hydrangea_paniculata")).kind == FORBIDDEN
    assert policy.assess(plant_catalog.get("cornus_alba")).kind == "official_main"
    assert policy.assess(plant_catalog.get("aesculus_hippocastanum")).entry is None


def test_additional_level_is_recognised(
    territories: TerritoryCatalog, texts: SelectionTexts, plant_catalog: PlantCatalog
) -> None:
    policy = policy_for(territories, texts, "residential_yard")
    assert policy.assess(plant_catalog.get("thuja_occidentalis")).kind == "official_additional"


def test_street_assortment_drops_species_the_official_table_forbids(
    plant_catalog: PlantCatalog,
    registry: InvasiveRegistry,
    territories: TerritoryCatalog,
    texts: SelectionTexts,
) -> None:
    street = suitability(plant_catalog, registry, territories, texts, "district_street")
    yard = suitability(plant_catalog, registry, territories, texts, "residential_yard")
    context = SiteContextDetector(carriageway_site(), SETTINGS).detect(Point(0, 3.0))
    assert "hydrangea_paniculata" not in ranked_keys(street.ranked(SHRUB, context))
    assert "hydrangea_paniculata" in ranked_keys(yard.ranked(SHRUB, context))
    assert "philadelphus" in ranked_keys(street.ranked(SHRUB, context))


def test_road_sensitive_species_are_kept_away_from_the_carriageway(
    plant_catalog: PlantCatalog,
    registry: InvasiveRegistry,
    territories: TerritoryCatalog,
    texts: SelectionTexts,
) -> None:
    street = suitability(plant_catalog, registry, territories, texts, "magistral")
    near_road = SiteContextDetector(carriageway_site(), SETTINGS).detect(Point(0, 3.0))
    far_away = SiteContextDetector(carriageway_site(), SETTINGS).detect(Point(0, 40.0))
    assert "pinus_sylvestris" not in ranked_keys(street.ranked(TREE, near_road))
    assert "pinus_sylvestris" in ranked_keys(street.ranked(TREE, far_away))


def test_species_with_the_spread_note_are_allowed_with_control(
    plant_catalog: PlantCatalog,
    registry: InvasiveRegistry,
    territories: TerritoryCatalog,
    texts: SelectionTexts,
) -> None:
    street = suitability(plant_catalog, registry, territories, texts, "district_street")
    context = SiteContextDetector(carriageway_site(), SETTINGS).detect(Point(0, 3.0))
    dogwood = next(item for item in street.ranked(SHRUB, context) if item.species.key == "cornus_alba")
    assert dogwood.invasive.status == ALLOWED_WITH_CONTROL
    assert "dpioos_assortment_notes" in dogwood.invasive.source_refs


def test_children_note_excludes_species_at_schools(
    territories: TerritoryCatalog, texts: SelectionTexts, plant_catalog: PlantCatalog
) -> None:
    school = policy_for(territories, texts, "school_kindergarten")
    street = policy_for(territories, texts, "residential_yard")
    barberry = plant_catalog.get("berberis")
    assert school.assess(barberry).kind == FORBIDDEN
    assert "примечание [2]" in school.exclusion_text(barberry)
    assert street.assess(barberry).admissible


def test_chosen_species_explains_the_official_table_its_notes_and_traits(
    plant_catalog: PlantCatalog,
    registry: InvasiveRegistry,
    territories: TerritoryCatalog,
    texts: SelectionTexts,
) -> None:
    street = suitability(plant_catalog, registry, territories, texts, "district_street")
    context = SiteContextDetector(carriageway_site(), SETTINGS).detect(Point(0, 3.0))
    lime = next(item for item in street.ranked(TREE, context) if item.species.key == "tilia_cordata")
    codes = {reason.code for reason in lime.reasons}
    assert "territory:official_main" in codes
    assert "territory:official_note" in codes
    assert "traits:dust_high_near_road" in codes
    assert any(reason.source_ref == "dpioos_assortment_main" for reason in lime.reasons)


def test_species_missing_from_the_official_table_fall_back_to_tsn(
    territories: TerritoryCatalog, texts: SelectionTexts, plant_catalog: PlantCatalog
) -> None:
    policy = policy_for(territories, texts, "park")
    assessment = policy.assess(plant_catalog.get("aesculus_hippocastanum"))
    assert assessment.entry is None
    assert assessment.kind in {RECOMMENDED, "limited", "unlisted", FORBIDDEN}


def test_species_of_the_noise_list_are_marked_on_noisy_streets(
    plant_catalog: PlantCatalog,
    registry: InvasiveRegistry,
    territories: TerritoryCatalog,
    texts: SelectionTexts,
) -> None:
    noisy = suitability(plant_catalog, registry, territories, texts, "magistral")
    quiet = suitability(plant_catalog, registry, territories, texts, "square")
    context = SiteContextDetector(carriageway_site(), SETTINGS).detect(Point(0, 3.0))
    on_street = next(item for item in noisy.ranked(TREE, context) if item.species.key == "tilia_cordata")
    on_square = next(item for item in quiet.ranked(TREE, context) if item.species.key == "tilia_cordata")
    assert "traits:noise_barrier" in {reason.code for reason in on_street.reasons}
    assert "traits:noise_barrier" not in {reason.code for reason in on_square.reasons}
    assert on_street.score - on_square.score == pytest.approx(SETTINGS.noise_bonus)


def test_excluded_species_are_listed_with_a_reason(
    plant_catalog: PlantCatalog,
    registry: InvasiveRegistry,
    territories: TerritoryCatalog,
    texts: SelectionTexts,
) -> None:
    street = suitability(plant_catalog, registry, territories, texts, "district_street")
    excluded = {species.name_ru: text for species, text in street.excluded(SHRUB)}
    assert any(name.startswith("Гортензия метельчатая") for name in excluded)
    assert any("примечание [5]" in text for text in excluded.values())
    assert all(excluded.values())


def test_assignment_lists_alternatives(
    toolkit: NormsToolkit,
    plant_catalog: PlantCatalog,
    registry: InvasiveRegistry,
    territories: TerritoryCatalog,
    texts: SelectionTexts,
) -> None:
    site = carriageway_site()
    street = suitability(plant_catalog, registry, territories, texts, "district_street")
    selector = SpeciesSelector(
        street, toolkit.evaluator(site), SiteContextDetector(site, SETTINGS), SETTINGS, texts
    )
    decision = toolkit.evaluator(site).evaluate(PlantCandidate("T-1", Point(0, 3.0), TREE, 5.0))
    outcome = selector.assign([decision])
    assignment = outcome.assignments[0]
    assert assignment.alternatives
    assert all(item.reason_ru for item in assignment.alternatives)
    assert outcome.territory_note is not None
    assert "улица районного значения" in outcome.territory_note.reason_ru
