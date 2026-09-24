from pathlib import Path

import pytest
from shapely.geometry import LineString, Point, box

from greenplan.domain.drawing import BlockReference, DrawingContent, LayerGeometry
from greenplan.domain.norms import SHRUB, TREE
from greenplan_ml.reference_extractor import ReferencePlantingExtractor
from greenplan_ml.shrub_area_fill import AreaFillSettings, ShrubAreaFill, along_axis, hexagonal_points

FILL = ShrubAreaFill(AreaFillSettings(shrub_spacing_m=1.0, single_shrub_max_area_m2=3.0))


def geometry(layer: str, shape, dxf_type: str = "HATCH") -> LayerGeometry:
    return LayerGeometry(layer, dxf_type, shape, "reference", "1")


def block(layer: str, x: float, y: float, name: str = "Липа") -> BlockReference:
    return BlockReference(layer, name, Point(x, y), 1.0, 0.0, (), "reference")


def test_group_area_is_filled_with_shrubs_at_the_design_spacing() -> None:
    points = FILL.positions([box(0, 0, 10, 10)])
    assert 100 <= len(points) <= 130
    assert all(box(0, 0, 10, 10).contains(point) for point in points)


def test_small_closed_outline_is_a_single_shrub() -> None:
    circle = Point(5, 5).buffer(0.8).exterior
    assert len(FILL.positions([LineString(circle.coords)])) == 1


def test_overlapping_hatch_and_outline_are_counted_once() -> None:
    outline = LineString(box(0, 0, 4, 4).exterior.coords)
    assert len(FILL.positions([box(0, 0, 4, 4), outline])) == len(FILL.positions([box(0, 0, 4, 4)]))


def test_narrow_hedge_gets_shrubs_along_its_axis() -> None:
    hedge = box(0, 0, 12, 0.4)
    assert hexagonal_points(hedge, 1.0) == [] or len(hexagonal_points(hedge, 1.0)) < 12
    assert 10 <= len(along_axis(hedge, 1.0)) <= 13
    assert len(FILL.positions([hedge])) >= 10


def test_open_lines_are_not_areas() -> None:
    assert FILL.positions([LineString([(0, 0), (10, 0)])]) == []


@pytest.fixture(scope="module")
def extractor(knowledge_root: Path) -> ReferencePlantingExtractor:
    return ReferencePlantingExtractor.from_knowledge(knowledge_root)


def test_area_drawn_shrub_layers_become_plantings(extractor: ReferencePlantingExtractor) -> None:
    content = DrawingContent(
        geometries=(
            geometry("! ПР СПИРЕЯ ВАНГУТТА", box(0, 0, 5, 5)),
            geometry("! ПР ДЕРЕВЬЯ", box(20, 20, 25, 25)),
            geometry("ДВ_ГП_П_Газон", box(0, 0, 50, 50)),
        ),
        annotations=(),
        block_references=(block("! ПР ДЕРЕВЬЯ", 22.0, 22.0),),
    )
    extracted = extractor.extract(content, "gp_parentheses")
    shrubs = [item for item in extracted.plantings if item.target == SHRUB]
    trees = [item for item in extracted.plantings if item.target == TREE]
    assert len(trees) == 1
    assert len(shrubs) > 20
    assert {item.species_ru for item in shrubs} == {"СПИРЕЯ ВАНГУТТА"}


def test_layers_with_shrub_blocks_are_not_filled_again(extractor: ReferencePlantingExtractor) -> None:
    content = DrawingContent(
        geometries=(geometry("PL_BUSH_Спирея", box(0, 0, 5, 5)),),
        annotations=(),
        block_references=(block("PL_BUSH_Спирея", 1.0, 1.0, "Спирея"),),
    )
    extracted = extractor.extract(content, "pl_prefix")
    assert len(extracted.plantings) == 1
