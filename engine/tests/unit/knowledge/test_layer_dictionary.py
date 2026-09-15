from pathlib import Path

import pytest

from greenplan.knowledge.layer_dictionary import LayerDictionary
from greenplan.knowledge.surface_codes import CARRIAGEWAY, LAWN, SIDEWALK, SurfaceCodeCatalog


@pytest.fixture(scope="module")
def dictionary(knowledge_root: Path) -> LayerDictionary:
    return LayerDictionary.from_file(knowledge_root / "dataset" / "mosgeotrest_layers.yaml")


@pytest.fixture(scope="module")
def surface_catalog(knowledge_root: Path) -> SurfaceCodeCatalog:
    return SurfaceCodeCatalog.from_file(knowledge_root / "dataset" / "surface_codes.yaml")


@pytest.mark.parametrize(
    ("layer", "expected_kind"),
    [
        ("Газопровод", "gas_pipeline"),
        ("Водопровод", "water_supply"),
        ("Канализация самотёчная", "sewer"),
        ("Теплосеть", "heating_network"),
        ("Кабель электрический", "power_cable"),
        ("Кабель связи", "communication_cable"),
        ("Общий коллектор", "utility_tunnel"),
        ("Здания", "building_wall"),
        ("Фонари", "lighting_pole"),
        ("Отдельно стоящее дерево", "existing_tree"),
    ],
)
def test_canonical_mosgeotrest_layers_are_classified(
    dictionary: LayerDictionary, layer: str, expected_kind: str
) -> None:
    classification = dictionary.classify(layer)
    assert classification.kind == expected_kind
    assert classification.is_known
    assert classification.confidence >= 0.9


def test_reexported_layer_name_is_normalized(dictionary: LayerDictionary) -> None:
    classification = dictionary.classify("Новый_Кабель связи_Ном._пера__15")
    assert classification.kind == "communication_cable"
    assert "mosgeotrest:up:Кабель связи" in classification.evidence


def test_projected_network_keeps_projected_status(dictionary: LayerDictionary) -> None:
    classification = dictionary.classify("Газопровод проектный")
    assert classification.kind == "gas_pipeline"
    assert classification.status == "projected"


def test_known_non_obstacle_layer_has_no_kind(dictionary: LayerDictionary) -> None:
    classification = dictionary.classify("Горизонтали")
    assert classification.is_known
    assert not classification.is_obstacle


def test_unknown_layer_is_reported_as_unknown(dictionary: LayerDictionary) -> None:
    classification = dictionary.classify("ывсаыу")
    assert not classification.is_known
    assert classification.confidence == 0.0


@pytest.mark.parametrize(
    ("layer", "expected_kind"),
    [
        ("ДВ_ГП_П_Граница работ", "site_boundary"),
        ("C-ROAD-LINE", "street_axis"),
        ("!!!_1. Дендра_сохранить", "existing_tree"),
        ("!!!_1. Дендра_вырубка", "tree_to_remove"),
        ("ДВ_ГП_П_Павильон_ООТ", "bus_shelter"),
    ],
)
def test_auxiliary_project_layers_are_classified(
    dictionary: LayerDictionary, layer: str, expected_kind: str
) -> None:
    assert dictionary.classify(layer).kind == expected_kind


@pytest.mark.parametrize(
    ("layer", "target_code", "target_class"),
    [
        ("_ГЗН-ГЗН", "ГЗН", LAWN),
        ("_АБ ТР-ГЗН (2 и более метров)", "ГЗН", LAWN),
        ("_ГЗН-АБ ТР", "АБ ТР", SIDEWALK),
        ("_АБ ПЧ-АБ ПЧ", "АБ ПЧ", CARRIAGEWAY),
        ("_ЩМА ПЧ-АБ ПЧ", "АБ ПЧ", CARRIAGEWAY),
    ],
)
def test_surface_layers_are_parsed_by_target_code(
    surface_catalog: SurfaceCodeCatalog, layer: str, target_code: str, target_class: str
) -> None:
    surface = surface_catalog.parse(layer)
    assert surface.target_code == target_code
    assert surface.target_class == target_class


def test_non_surface_layer_is_not_parsed(surface_catalog: SurfaceCodeCatalog) -> None:
    assert surface_catalog.parse("Газопровод") is None
