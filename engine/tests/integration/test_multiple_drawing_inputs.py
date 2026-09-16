from pathlib import Path

import pytest

from greenplan.cli.commands import InspectCommand, RunCommand, VerifyCommand, select_inputs
from greenplan.cli.main import build_parser
from greenplan.domain.errors import InvalidInputError
from greenplan.ingest.drawing_content_reader import DrawingContentReader
from greenplan.ingest.drawing_file_opener import DrawingFileOpener, DxfDocumentLoader
from greenplan.ingest.drawing_set_builder import DrawingSetBuilder
from greenplan.ingest.input_selection import DrawingInputSelector
from greenplan.ingest.xref_reference_reader import XrefReferenceReader

from fixtures.drawing_factory import (
    add_polyline,
    add_text,
    add_xref,
    create_document,
    rectangle,
    save_document,
)


def separate_inputs(root: Path) -> tuple[Path, Path]:
    general_plan = create_document()
    add_polyline(general_plan, "ДВ_ГП_П_Граница работ", rectangle(0, 0, 60, 20), closed=True)
    base = create_document()
    add_polyline(base, "Газопровод", [(0, 10), (60, 10)])
    add_text(base, "Газопровод", "d=110н.д.п/э", (10, 10.5))
    return (
        save_document(general_plan, root / "Генплан ул Примерная.dxf"),
        save_document(base, root / "Геоподоснова.dxf"),
    )


def builder() -> DrawingSetBuilder:
    return DrawingSetBuilder(DrawingFileOpener(DxfDocumentLoader(), converter=None), XrefReferenceReader())


def test_general_plan_is_chosen_as_main_among_separate_files(tmp_path: Path) -> None:
    general_plan, base = separate_inputs(tmp_path)
    inputs = DrawingInputSelector().select([base, general_plan])
    assert inputs.main == general_plan
    assert inputs.overlays == (base,)


def test_directory_input_takes_top_level_drawings(tmp_path: Path) -> None:
    general_plan, base = separate_inputs(tmp_path)
    save_document(create_document(), tmp_path / "ссылки" / "Борт.dxf")
    inputs = DrawingInputSelector().select([tmp_path])
    assert inputs.main == general_plan
    assert inputs.overlays == (base,)
    assert inputs.search_root == tmp_path


def test_explicit_main_wins_over_the_name_hint(tmp_path: Path) -> None:
    general_plan, base = separate_inputs(tmp_path)
    inputs = DrawingInputSelector().select([general_plan, base], main=base)
    assert inputs.main == base
    assert inputs.overlays == (general_plan,)


def test_mosgeotrest_tile_is_never_chosen_as_main(tmp_path: Path) -> None:
    big_tile = create_document()
    for offset in range(200):
        add_polyline(big_tile, "Газопровод", [(0, offset), (60, offset)])
    tile = save_document(big_tile, tmp_path / "output[1-7]_3_ДЖКХ-25_05352up.dxf")
    plan = save_document(create_document(), tmp_path / "Схема.dxf")
    assert DrawingInputSelector().select([tile, plan]).main == plan


def test_dxf_copy_replaces_a_dwg_of_the_same_name(tmp_path: Path) -> None:
    general_plan, _base = separate_inputs(tmp_path)
    dwg = tmp_path / "Генплан ул Примерная.dwg"
    dwg.write_bytes(b"AC1032")
    inputs = DrawingInputSelector().select([tmp_path])
    assert dwg not in (inputs.main, *inputs.overlays)
    assert inputs.main == general_plan


def test_missing_input_is_reported(tmp_path: Path) -> None:
    with pytest.raises(InvalidInputError):
        DrawingInputSelector().select([tmp_path / "absent.dxf"])


def test_empty_directory_is_reported(tmp_path: Path) -> None:
    with pytest.raises(InvalidInputError):
        DrawingInputSelector().select([tmp_path])


def test_overlay_geometry_joins_the_site_content(tmp_path: Path) -> None:
    general_plan, base = separate_inputs(tmp_path)
    drawing_set = builder().build(general_plan, tmp_path, (base,))
    content = DrawingContentReader().read(drawing_set)
    assert {"ДВ_ГП_П_Граница работ", "Газопровод"} <= content.layer_names()
    assert content.geometries_on("Газопровод")[0].source_name == "Геоподоснова"


def test_overlay_already_loaded_as_xref_is_not_duplicated(tmp_path: Path) -> None:
    general_plan, base = separate_inputs(tmp_path)
    main = create_document()
    add_polyline(main, "ДВ_ГП_П_Граница работ", rectangle(0, 0, 60, 20), closed=True)
    add_xref(main, "base", r".\Геоподоснова.dwg")
    main_path = save_document(main, tmp_path / "Генплан со ссылкой.dxf")
    drawing_set = builder().build(main_path, tmp_path, (base, general_plan))
    content = DrawingContentReader().read(drawing_set)
    assert len(content.geometries_on("Газопровод")) == 1
    assert len(drawing_set.references) == 2


def test_cli_accepts_several_inputs_and_an_explicit_main(tmp_path: Path) -> None:
    general_plan, base = separate_inputs(tmp_path)
    parser = build_parser((RunCommand(), VerifyCommand(), InspectCommand()))
    command = ["run", "--input", str(general_plan), str(base), "--main", str(base)]
    arguments = parser.parse_args([*command, "--output", str(tmp_path / "out")])
    inputs = select_inputs(arguments)
    assert inputs.main == base
    assert inputs.overlays == (general_plan,)
