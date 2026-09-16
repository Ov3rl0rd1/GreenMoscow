from pathlib import Path

import pytest

from greenplan.domain.site import SiteModel
from greenplan.ingest.drawing_content_reader import DrawingContentReader
from greenplan.ingest.drawing_file_opener import DrawingFileOpener, DxfDocumentLoader
from greenplan.ingest.drawing_set_builder import DrawingSetBuilder
from greenplan.ingest.dwg_converter import LibreDwgConverter
from greenplan.ingest.folder_converter import FolderConverter, drawings_under
from greenplan.ingest.input_selection import DrawingInputSelector
from greenplan.ingest.xref_reference_reader import XrefReferenceReader
from greenplan.recognition.site_model_builder import SiteModelBuilder

from fixtures.pilot_objects import BAGRITSKOGO_MAIN

pytestmark = [pytest.mark.realdata, pytest.mark.slow]


@pytest.fixture(scope="module")
def dxf_object(
    pilot_objects_root: Path,
    dwg2dxf_path: Path,
    repository_root: Path,
    tmp_path_factory: pytest.TempPathFactory,
) -> Path:
    converter = LibreDwgConverter(dwg2dxf_path, repository_root / "data" / "cache" / "converted")
    target = tmp_path_factory.mktemp("dxf_object")
    result = FolderConverter(converter).convert(pilot_objects_root / BAGRITSKOGO_MAIN.parent, target)
    assert not result.failed
    return target


@pytest.fixture(scope="module")
def dxf_site(dxf_object: Path, knowledge_root: Path) -> SiteModel:
    inputs = DrawingInputSelector().select([dxf_object])
    builder = DrawingSetBuilder(DrawingFileOpener(DxfDocumentLoader(), converter=None), XrefReferenceReader())
    drawing_set = builder.build(inputs.main, inputs.search_root, inputs.overlays)
    content = DrawingContentReader().read(drawing_set)
    return SiteModelBuilder.from_knowledge(knowledge_root).build(content, drawing_set.unresolved_references)


def test_every_drawing_of_the_object_has_a_dxf_twin(pilot_objects_root: Path, dxf_object: Path) -> None:
    sources = list(drawings_under(pilot_objects_root / BAGRITSKOGO_MAIN.parent))
    assert len(list(dxf_object.rglob("*.dxf"))) == len(sources)


def test_folder_input_picks_the_general_plan(dxf_object: Path) -> None:
    inputs = DrawingInputSelector().select([dxf_object])
    assert inputs.main.stem == BAGRITSKOGO_MAIN.stem
    assert inputs.overlays == ()


def test_dxf_only_object_is_recognised_like_the_dwg_one(
    dxf_site: SiteModel, bagritskogo_site: SiteModel
) -> None:
    assert dxf_site.diagnostics.obstacle_counts == bagritskogo_site.diagnostics.obstacle_counts
    assert dxf_site.boundary.area == pytest.approx(bagritskogo_site.boundary.area, rel=1e-6)
    assert dxf_site.plantable_surface.area == pytest.approx(bagritskogo_site.plantable_surface.area, rel=1e-6)
    assert len(dxf_site.kept_trees()) == len(bagritskogo_site.kept_trees())
    assert dxf_site.diagnostics.unresolved_references == bagritskogo_site.diagnostics.unresolved_references
