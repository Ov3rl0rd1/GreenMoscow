from pathlib import Path

import pytest

from fixtures.pilot_objects import BAGRITSKOGO_MAIN, LoadedPilotObject, load_pilot_object

pytestmark = [pytest.mark.realdata, pytest.mark.converter, pytest.mark.slow]


@pytest.fixture(scope="module")
def bagritskogo(pilot_objects_root: Path, dwg2dxf_path: Path, repository_root: Path) -> LoadedPilotObject:
    return load_pilot_object(pilot_objects_root, BAGRITSKOGO_MAIN, dwg2dxf_path, repository_root)


def test_main_drawing_resolves_mosgeotrest_tiles(bagritskogo: LoadedPilotObject) -> None:
    drawing_set = bagritskogo.drawing_set
    reference_names = {drawing.name for drawing in drawing_set.references}
    assert len(drawing_set.references) + len(drawing_set.unresolved_references) == 42
    assert len(drawing_set.references) >= 25
    assert any(name.endswith("up") for name in reference_names)
    assert any(name.endswith("tp") for name in reference_names)


def test_missing_project_tiles_are_reported_as_unresolved(bagritskogo: LoadedPilotObject) -> None:
    assert any("ДЖКХпр-25_05352" in declared for declared in bagritskogo.drawing_set.unresolved_references)


def test_underground_networks_and_annotations_are_extracted(bagritskogo: LoadedPilotObject) -> None:
    content = bagritskogo.content
    assert len(content.geometries_on("Газопровод")) > 100
    assert len(content.geometries_on("Теплосеть")) > 50
    assert sum(1 for item in content.annotations_on("Газопровод") if item.text.startswith("d=")) > 50


def test_work_boundary_and_lawn_surfaces_are_present(bagritskogo: LoadedPilotObject) -> None:
    content = bagritskogo.content
    assert content.geometries_on("ДВ_ГП_П_Граница работ")
    assert sum(item.geometry.area for item in content.geometries_on("_ГЗН-ГЗН")) > 100.0


def test_tiles_and_boundary_share_coordinate_frame(bagritskogo: LoadedPilotObject) -> None:
    content = bagritskogo.content
    boundary = content.geometries_on("ДВ_ГП_П_Граница работ")[0].geometry
    assert any(item.geometry.distance(boundary) < 200 for item in content.geometries_on("Газопровод"))
