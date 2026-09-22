import re
from pathlib import Path

import ezdxf
from hypothesis import given, settings
from hypothesis import strategies as st

from greenplan.export.entity_fingerprint import EntityFingerprinter
from greenplan.export.layer_names import LayerNameSanitizer

from fixtures.drawing_factory import (
    add_block_reference,
    add_hatch,
    add_line,
    add_text,
    create_document,
    rectangle,
    save_document,
)

SANITIZER = LayerNameSanitizer(40)
FINGERPRINTER = EntityFingerprinter()
VALID_LAYER_NAME = re.compile(r"^[A-Z0-9_-]+$")


def test_species_layer_name_is_latin_uppercase() -> None:
    assert SANITIZER.join("AI", "PL_TREES", "tilia_cordata", "") == "AI_PL_TREES_TILIA_CORDATA"


def test_cyrillic_and_forbidden_characters_are_replaced() -> None:
    assert SANITIZER.sanitize("Липа <мелколистная>/2") == "2"
    assert SANITIZER.sanitize("Газопровод") == "UNNAMED"


@settings(max_examples=200, deadline=None)
@given(st.text())
def test_any_text_becomes_valid_bounded_idempotent_layer_name(text: str) -> None:
    name = SANITIZER.sanitize(text)
    assert VALID_LAYER_NAME.match(name)
    assert len(name) <= 40
    assert SANITIZER.sanitize(name) == name


def sample_drawing(path: Path) -> Path:
    document = create_document()
    add_line(document, "Газопровод", (0, 0), (10, 0))
    add_hatch(document, "_ГЗН-ГЗН", rectangle(0, 5, 10, 9))
    add_text(document, "Газопровод", "d=110", (2, 0.5))
    add_block_reference(document, "!!!_1. Дендра_сохранить", "TREE", (5, 7), {"N": "1"})
    return save_document(document, path)


def test_reloaded_document_has_identical_fingerprints(tmp_path: Path) -> None:
    path = sample_drawing(tmp_path / "sample.dxf")
    first = FINGERPRINTER.modelspace_fingerprints(ezdxf.readfile(path))
    second = FINGERPRINTER.modelspace_fingerprints(ezdxf.readfile(path))
    assert len(first) == 4
    assert FINGERPRINTER.compare(first, second).is_intact


def test_resaved_document_keeps_fingerprints(tmp_path: Path) -> None:
    path = sample_drawing(tmp_path / "sample.dxf")
    resaved = tmp_path / "resaved.dxf"
    ezdxf.readfile(path).saveas(resaved)
    before = FINGERPRINTER.modelspace_fingerprints(ezdxf.readfile(path))
    assert FINGERPRINTER.compare(
        before, FINGERPRINTER.modelspace_fingerprints(ezdxf.readfile(resaved))
    ).is_intact


def test_moved_vertex_changed_layer_and_deleted_entity_are_detected(tmp_path: Path) -> None:
    path = sample_drawing(tmp_path / "sample.dxf")
    before = FINGERPRINTER.modelspace_fingerprints(ezdxf.readfile(path))
    document = ezdxf.readfile(path)
    line, hatch, text, _insert = list(document.modelspace())
    hatch_handle = hatch.dxf.handle
    line.dxf.end = (10, 1)
    text.dxf.layer = "0"
    document.modelspace().delete_entity(hatch)
    difference = FINGERPRINTER.compare(before, FINGERPRINTER.modelspace_fingerprints(document))
    assert difference.missing_handles == (hatch_handle,)
    assert set(difference.changed_handles) == {line.dxf.handle, text.dxf.handle}


def test_integer_and_float_forms_of_one_value_have_equal_fingerprints() -> None:
    document = create_document()
    add_block_reference(document, "МАФ", "BENCH", (5, 7))
    insert = next(iter(document.modelspace()))
    insert.dxf.zscale = 1.0
    as_float = FINGERPRINTER.fingerprint(insert)
    insert.dxf.zscale = 1
    assert FINGERPRINTER.fingerprint(insert) == as_float


def test_text_with_broken_encoding_is_fingerprinted_without_failure() -> None:
    document = create_document()
    text = document.modelspace().add_text("примечание", dxfattribs={"layer": "ПРИМ"})
    text.dxf.text = "смотровы\udcd1\udc85 колодцах"
    first = FINGERPRINTER.fingerprint(text)
    assert first == FINGERPRINTER.fingerprint(text)
    text.dxf.text = "смотровых колодцах"
    assert FINGERPRINTER.fingerprint(text) == first


def test_empty_acis_body_is_reported_apart_from_lost_entities() -> None:
    document = create_document()
    region = document.modelspace().add_region([])
    line = document.modelspace().add_line((0, 0), (1, 0))
    region_handle, line_handle = region.dxf.handle, line.dxf.handle
    before = FINGERPRINTER.modelspace_fingerprints(document)
    document.modelspace().delete_entity(region)
    difference = FINGERPRINTER.compare(before, FINGERPRINTER.modelspace_fingerprints(document))
    assert difference.dropped_empty_bodies == (region_handle,)
    assert difference.missing_handles == ()
    assert difference.is_intact
    document.modelspace().delete_entity(line)
    lost = FINGERPRINTER.compare(before, FINGERPRINTER.modelspace_fingerprints(document))
    assert lost.missing_handles == (line_handle,)
    assert not lost.is_intact
