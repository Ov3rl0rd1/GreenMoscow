import math

import pytest
from ezdxf.math import Matrix44

from greenplan.ingest.entity_geometry import (
    BlockReferenceExtractor,
    EntityGeometryExtractor,
    TextAnnotationExtractor,
)

from fixtures.drawing_factory import (
    add_block_reference,
    add_circle,
    add_hatch,
    add_line,
    add_polyline,
    add_text,
    create_document,
    rectangle,
)

IDENTITY = Matrix44()


def only_entity(document):
    return next(iter(document.modelspace()))


def test_line_becomes_linestring_with_same_length() -> None:
    document = create_document()
    add_line(document, "Газопровод", (0, 0), (3, 4))
    geometry = EntityGeometryExtractor().extract(only_entity(document), IDENTITY)
    assert geometry.geom_type == "LineString"
    assert geometry.length == pytest.approx(5.0)


def test_polyline_with_bulge_is_flattened_close_to_arc_length() -> None:
    document = create_document()
    document.layers.add("Теплосеть")
    document.modelspace().add_lwpolyline([(0, 0, 0, 0, 1.0), (2, 0, 0, 0, 0)], format="xyseb")
    geometry = EntityGeometryExtractor(max_sagitta_m=0.001).extract(only_entity(document), IDENTITY)
    assert geometry.length == pytest.approx(math.pi, rel=1e-2)


def test_circle_becomes_closed_ring() -> None:
    document = create_document()
    add_circle(document, "Колодцы", (10, 10), 1.0)
    geometry = EntityGeometryExtractor(max_sagitta_m=0.001).extract(only_entity(document), IDENTITY)
    assert geometry.is_ring
    assert geometry.length == pytest.approx(2 * math.pi, rel=1e-2)


def test_hatch_with_hole_uses_even_odd_area() -> None:
    document = create_document()
    add_hatch(document, "_ГЗН-ГЗН", rectangle(0, 0, 10, 10), holes=[rectangle(2, 2, 4, 4)])
    geometry = EntityGeometryExtractor().extract(only_entity(document), IDENTITY)
    assert geometry.area == pytest.approx(96.0)


def test_transform_translates_geometry() -> None:
    document = create_document()
    add_polyline(document, "Бортовой камень", [(0, 0), (1, 0)])
    geometry = EntityGeometryExtractor().extract(only_entity(document), Matrix44.translate(100, 200, 0))
    assert geometry.coords[0] == pytest.approx((100.0, 200.0))


def test_unsupported_entity_returns_none() -> None:
    document = create_document()
    document.modelspace().add_mtext("x")
    assert EntityGeometryExtractor().extract(only_entity(document), IDENTITY) is None


def test_text_annotation_keeps_text_position_and_rotation() -> None:
    document = create_document()
    add_text(document, "Газопровод", "d=219н.д.ст.", (5, 6), rotation_deg=274.0)
    annotation = TextAnnotationExtractor().extract(only_entity(document), Matrix44.translate(1, 1, 0), "up")
    assert annotation.text == "d=219н.д.ст."
    assert (annotation.position.x, annotation.position.y) == pytest.approx((6.0, 7.0))
    assert annotation.rotation_deg == pytest.approx(274.0)
    assert annotation.source_name == "up"


def test_blank_text_is_ignored() -> None:
    document = create_document()
    add_text(document, "Газопровод", "   ", (0, 0))
    assert TextAnnotationExtractor().extract(only_entity(document), IDENTITY, "up") is None


def test_block_reference_keeps_position_scale_and_attributes() -> None:
    document = create_document()
    add_block_reference(document, "!!!_1. Дендра_сохранить", "tree", (3, 4), {"ХАР.ТОЧКА": "17"})
    insert = next(iter(document.modelspace().query("INSERT")))
    reference = BlockReferenceExtractor().extract(insert, Matrix44.scale(2, 2, 1), "dendro")
    assert (reference.position.x, reference.position.y) == pytest.approx((6.0, 8.0))
    assert reference.scale == pytest.approx(2.0)
    assert reference.attribute("ХАР.ТОЧКА") == "17"
