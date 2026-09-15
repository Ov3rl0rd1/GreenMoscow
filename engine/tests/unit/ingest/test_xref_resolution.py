from pathlib import Path

import pytest

from greenplan.ingest.xref_file_locator import XrefFileLocator
from greenplan.ingest.xref_reference_reader import XrefReferenceReader

from fixtures.drawing_factory import add_xref, create_document, save_document


def touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    return path


def test_reader_returns_declared_path_and_insert_transform() -> None:
    document = create_document()
    add_xref(document, "tile_up", r".\3ДЖКХ-25_05352\output[1-7]_up.dwg", insert=(10.0, 20.0))
    references = XrefReferenceReader().read(document)
    assert len(references) == 1
    assert references[0].declared_path == r".\3ДЖКХ-25_05352\output[1-7]_up.dwg"
    origin = references[0].transform.transform((0, 0, 0))
    assert (origin.x, origin.y) == pytest.approx((10.0, 20.0))


def test_reader_skips_duplicate_inserts_of_same_xref() -> None:
    document = create_document()
    add_xref(document, "boundary", "boundary.dwg")
    document.modelspace().add_blockref("boundary", (0, 0))
    assert len(XrefReferenceReader().read(document)) == 1


def test_locator_resolves_relative_windows_path(tmp_path: Path) -> None:
    expected = touch(tmp_path / "3ДЖКХ-25_05352" / "output[1-7]_up.dwg")
    located = XrefFileLocator(tmp_path).locate(r".\3ДЖКХ-25_05352\output[1-7]_up.dwg", tmp_path)
    assert located == expected


def test_locator_falls_back_to_file_name_search(tmp_path: Path) -> None:
    expected = touch(tmp_path / "ссылки" / "Граница работ.dwg")
    located = XrefFileLocator(tmp_path).locate(r"C:\Users\designer\Граница работ.dwg", tmp_path)
    assert located == expected


def test_locator_accepts_converted_dxf_with_same_stem(tmp_path: Path) -> None:
    expected = touch(tmp_path / "tiles" / "output[1]_tp.dxf")
    assert XrefFileLocator(tmp_path).locate("output[1]_tp.dwg", tmp_path) == expected


def test_locator_prefers_closest_copy(tmp_path: Path) -> None:
    main_directory = tmp_path / "Исходные данные"
    touch(tmp_path / "Проектное решение" / "tile.dwg")
    closest = touch(main_directory / "tiles" / "tile.dwg")
    assert XrefFileLocator(tmp_path).locate("tile.dwg", main_directory) == closest


def test_locator_ignores_tar_pax_headers(tmp_path: Path) -> None:
    touch(tmp_path / "PaxHeader" / "tile.dwg")
    assert XrefFileLocator(tmp_path).locate("tile.dwg", tmp_path) is None


def test_locator_returns_none_for_missing_file(tmp_path: Path) -> None:
    assert XrefFileLocator(tmp_path).locate("absent.dwg", tmp_path) is None


def test_saved_document_round_trip_keeps_xref(tmp_path: Path) -> None:
    document = create_document()
    add_xref(document, "tile", "tile.dxf")
    saved = save_document(document, tmp_path / "main.dxf")
    import ezdxf

    reloaded = ezdxf.readfile(saved)
    assert XrefReferenceReader().read(reloaded)[0].declared_path == "tile.dxf"
