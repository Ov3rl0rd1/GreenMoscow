from pathlib import Path

import pytest

from greenplan.domain.errors import DrawingLoadError
from greenplan.ingest.drawing_content_reader import DrawingContentReader
from greenplan.ingest.drawing_file_opener import DrawingFileOpener, DxfDocumentLoader
from greenplan.ingest.drawing_set_builder import DrawingSetBuilder
from greenplan.ingest.xref_reference_reader import XrefReferenceReader

from fixtures.drawing_factory import (
    add_hatch,
    add_polyline,
    add_text,
    add_xref,
    create_document,
    rectangle,
    save_document,
)


def build_object_folder(root: Path) -> Path:
    tile = create_document()
    add_polyline(tile, "Газопровод", [(0, 0), (50, 0)])
    add_text(tile, "Газопровод", "d=110н.д.п/э", (10, 1))
    save_document(tile, root / "3ДЖКХ-25_00001" / "output[1]_3_ДЖКХ-25_00001up.dxf")
    surfaces = create_document()
    add_hatch(surfaces, "_ГЗН-ГЗН", rectangle(0, 2, 50, 6))
    save_document(surfaces, root / "ссылки" / "Заливка.dxf")
    main = create_document()
    add_polyline(main, "ДВ_ГП_П_Граница работ", rectangle(-5, -5, 55, 10), closed=True)
    add_xref(main, "tile_up", r".\3ДЖКХ-25_00001\output[1]_3_ДЖКХ-25_00001up.dwg", insert=(1000.0, 0.0))
    add_xref(main, "surfaces", r".\ссылки\Заливка.dwg", insert=(1000.0, 0.0))
    add_xref(main, "missing", "absent.dwg")
    return save_document(main, root / "main.dxf")


def builder() -> DrawingSetBuilder:
    return DrawingSetBuilder(DrawingFileOpener(DxfDocumentLoader(), converter=None), XrefReferenceReader())


def test_drawing_set_contains_resolved_and_unresolved_references(tmp_path: Path) -> None:
    drawing_set = builder().build(build_object_folder(tmp_path))
    assert {drawing.name for drawing in drawing_set.references} == {"tile_up", "surfaces"}
    assert drawing_set.unresolved_references == ("absent.dwg",)


def test_content_places_xref_geometry_in_world_coordinates(tmp_path: Path) -> None:
    content = DrawingContentReader().read(builder().build(build_object_folder(tmp_path)))
    gas = content.geometries_on("Газопровод")[0]
    assert gas.source_name == "tile_up"
    assert gas.geometry.bounds[0] == pytest.approx(1000.0)
    assert content.annotations_on("Газопровод")[0].position.x == pytest.approx(1010.0)
    assert content.geometries_on("_ГЗН-ГЗН")[0].geometry.area == pytest.approx(200.0)


def test_content_includes_main_drawing_entities(tmp_path: Path) -> None:
    content = DrawingContentReader().read(builder().build(build_object_folder(tmp_path)))
    assert "ДВ_ГП_П_Граница работ" in content.layer_names()


def test_dwg_input_without_converter_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "main.dwg"
    source.write_bytes(b"AC1032")
    with pytest.raises(DrawingLoadError):
        builder().build(source)
