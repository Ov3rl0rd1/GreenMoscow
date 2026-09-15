from pathlib import Path

import pytest
from shapely.geometry import LineString

from greenplan.domain.drawing import LayerGeometry
from greenplan.domain.obstacle_kinds import SITE_BOUNDARY, SURVEY_BOUNDARY
from greenplan.domain.site import BOUNDARY_GAP_CLOSED
from greenplan.knowledge.layer_dictionary import LayerDictionary
from greenplan.recognition.site_boundary_extractor import WORK_BOUNDARY_SOURCE, SiteBoundaryExtractor


@pytest.fixture(scope="module")
def dictionary(knowledge_root: Path) -> LayerDictionary:
    return LayerDictionary.from_file(knowledge_root / "dataset" / "mosgeotrest_layers.yaml")


@pytest.mark.parametrize(
    "layer",
    [
        "ДВ_ГП_П_Граница работ",
        "_ГП_граница благоустройства",
        "!!!_1. ГРАНИЦА РАБОТ",
        "Граница проектирования",
    ],
)
def test_work_boundary_layer_variants_are_recognized(dictionary: LayerDictionary, layer: str) -> None:
    assert dictionary.classify(layer).kind == SITE_BOUNDARY


def test_order_boundary_in_any_case_is_survey_boundary(dictionary: LayerDictionary) -> None:
    assert dictionary.classify("Граница Заказа").kind == SURVEY_BOUNDARY


def test_dendro_survey_boundary_is_not_a_work_boundary(dictionary: LayerDictionary) -> None:
    assert dictionary.classify("!!!_1. ГРАНИЦА ДЕНДРОИЗЫСКАНИЙ").kind != SITE_BOUNDARY


def test_unclosed_work_boundary_is_repaired_and_reported(dictionary: LayerDictionary) -> None:
    layer = "_ГП_граница благоустройства"
    outline = LineString([(0.95, 0), (100, 0), (100, 50), (0, 50), (0, 0)])
    geometries = [LayerGeometry(layer, "LWPOLYLINE", outline, "xref_граница", "A")]
    boundary = SiteBoundaryExtractor(25.0).extract(geometries, {layer: dictionary.classify(layer)})
    assert boundary.source == WORK_BOUNDARY_SOURCE
    assert boundary.area.area == pytest.approx(5000.0)
    assert boundary.repairs[0].code == BOUNDARY_GAP_CLOSED
