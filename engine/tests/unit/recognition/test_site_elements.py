from pathlib import Path

import pytest
from shapely.geometry import LineString, Point, Polygon

from greenplan.domain.drawing import BlockReference, LayerGeometry
from greenplan.knowledge.layer_dictionary import LayerDictionary
from greenplan.recognition.existing_tree_extractor import ExistingTreeExtractor
from greenplan.recognition.site_boundary_extractor import (
    CONTENT_EXTENT_SOURCE,
    SURVEY_BOUNDARY_SOURCE,
    WORK_BOUNDARY_SOURCE,
    SiteBoundaryExtractor,
)
from greenplan.recognition.symbol_clusterer import SymbolClusterer

from fixtures.drawing_factory import rectangle


@pytest.fixture(scope="module")
def dictionary(knowledge_root: Path) -> LayerDictionary:
    return LayerDictionary.from_file(knowledge_root / "dataset" / "mosgeotrest_layers.yaml")


def closed_line(layer: str, coordinates, source: str = "main") -> LayerGeometry:
    ring = list(coordinates) + [coordinates[0]]
    return LayerGeometry(layer, "LWPOLYLINE", LineString(ring), source, "A")


def classifications_for(dictionary: LayerDictionary, geometries) -> dict:
    return {item.layer: dictionary.classify(item.layer) for item in geometries}


def test_work_boundary_is_preferred(dictionary: LayerDictionary) -> None:
    geometries = [
        closed_line("ДВ_ГП_П_Граница работ", rectangle(0, 0, 50, 20)),
        closed_line("Граница заказа", rectangle(-100, -100, 100, 100)),
    ]
    boundary = SiteBoundaryExtractor(25.0).extract(geometries, classifications_for(dictionary, geometries))
    assert boundary.source == WORK_BOUNDARY_SOURCE
    assert boundary.area.area == pytest.approx(1000.0)


def test_survey_boundary_is_used_without_work_boundary(dictionary: LayerDictionary) -> None:
    geometries = [closed_line("Граница заказа", rectangle(0, 0, 10, 10))]
    boundary = SiteBoundaryExtractor(25.0).extract(geometries, classifications_for(dictionary, geometries))
    assert boundary.source == SURVEY_BOUNDARY_SOURCE


def test_content_extent_is_last_resort(dictionary: LayerDictionary) -> None:
    geometries = [LayerGeometry("Газопровод", "LINE", LineString([(0, 0), (30, 40)]), "up", "B")]
    boundary = SiteBoundaryExtractor(25.0).extract(geometries, classifications_for(dictionary, geometries))
    assert boundary.source == CONTENT_EXTENT_SOURCE
    assert boundary.area.area == pytest.approx(1200.0)


def test_tiny_closed_contours_are_not_boundaries(dictionary: LayerDictionary) -> None:
    geometries = [
        closed_line("ДВ_ГП_П_Граница работ", rectangle(0, 0, 2, 2)),
        closed_line("Граница заказа", rectangle(0, 0, 20, 20)),
    ]
    boundary = SiteBoundaryExtractor(25.0).extract(geometries, classifications_for(dictionary, geometries))
    assert boundary.source == SURVEY_BOUNDARY_SOURCE


def test_symbols_are_clustered_into_single_positions() -> None:
    clusterer = SymbolClusterer(cluster_gap_m=0.25, max_symbol_size_m=3.0)
    first_symbol = [Point(0, 0).buffer(0.2).exterior, LineString([(-0.5, 0), (0.5, 0)])]
    second_symbol = [Point(10, 0).buffer(0.2).exterior]
    positions = clusterer.symbol_positions(first_symbol + second_symbol)
    assert sorted(round(position.x) for position in positions) == [0, 10]


def test_large_drawings_are_not_symbols() -> None:
    clusterer = SymbolClusterer(cluster_gap_m=0.25, max_symbol_size_m=3.0)
    assert clusterer.symbol_positions([LineString([(0, 0), (20, 0)])]) == []


def test_existing_trees_combine_dendro_blocks_and_topographic_symbols(dictionary: LayerDictionary) -> None:
    dendro = BlockReference("!!!_1. Дендра_сохранить", "*U135", Point(0, 0), 1.0, 0.0, (), "dendro")
    removed = BlockReference("!!!_1. Дендра_вырубка", "*U136", Point(5, 0), 1.0, 0.0, (), "dendro")
    duplicate_symbol = LayerGeometry(
        "Отдельно стоящее дерево", "ARC", Point(0.3, 0).buffer(0.21).exterior, "tp", "C"
    )
    new_symbol = LayerGeometry(
        "Отдельно стоящее дерево", "ARC", Point(20, 0).buffer(0.21).exterior, "tp", "D"
    )
    geometries = [duplicate_symbol, new_symbol]
    layers = [*geometries, dendro, removed]
    classifications = {item.layer: dictionary.classify(item.layer) for item in layers}
    extractor = ExistingTreeExtractor(SymbolClusterer(0.25, 3.0), duplicate_distance_m=1.0)
    trees = extractor.extract(geometries, [dendro, removed], classifications)
    assert len(trees) == 3
    assert sorted(tree.status for tree in trees) == ["keep", "keep", "remove"]
    assert isinstance(trees[0].position, Point)
    assert not any(isinstance(tree.position, Polygon) for tree in trees)
