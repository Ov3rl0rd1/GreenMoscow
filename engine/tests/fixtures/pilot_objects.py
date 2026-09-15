from dataclasses import dataclass
from pathlib import Path

from greenplan.domain.drawing import DrawingContent, DrawingSet
from greenplan.ingest.drawing_content_reader import DrawingContentReader
from greenplan.ingest.drawing_file_opener import DrawingFileOpener, DxfDocumentLoader
from greenplan.ingest.drawing_set_builder import DrawingSetBuilder
from greenplan.ingest.dwg_converter import LibreDwgConverter
from greenplan.ingest.xref_reference_reader import XrefReferenceReader

BAGRITSKOGO_MAIN = (
    Path("5. Багрицкого улица")
    / "Исходные данные"
    / "10000450_ул Багрицкого_ГП и ПБ"
    / "ГП и ПБ ул Багрицкого.dwg"
)


@dataclass(frozen=True)
class LoadedPilotObject:
    drawing_set: DrawingSet
    content: DrawingContent


def load_pilot_object(
    pilot_objects_root: Path, main_relative_path: Path, dwg2dxf_path: Path, repository_root: Path
) -> LoadedPilotObject:
    converter = LibreDwgConverter(dwg2dxf_path, repository_root / "data" / "cache" / "converted")
    builder = DrawingSetBuilder(DrawingFileOpener(DxfDocumentLoader(), converter), XrefReferenceReader())
    drawing_set = builder.build(pilot_objects_root / main_relative_path)
    return LoadedPilotObject(drawing_set, DrawingContentReader().read(drawing_set))
