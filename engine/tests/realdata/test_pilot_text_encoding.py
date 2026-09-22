from pathlib import Path

import pytest

from greenplan.export.entity_fingerprint import EntityFingerprinter
from greenplan.ingest.drawing_file_opener import DrawingFileOpener, DxfDocumentLoader
from greenplan.ingest.dwg_converter import LibreDwgConverter

pytestmark = [pytest.mark.realdata, pytest.mark.converter, pytest.mark.slow]

MIXED_ENCODING_DRAWING = (
    Path("4. Харьковская улица")
    / "Исходные данные"
    / "Генплан Харьковская"
    / "Харьковская АПОТ_2026-01-15.dwg"
)


def test_drawing_with_mixed_encoding_can_be_fingerprinted(
    pilot_objects_root: Path, dwg2dxf_path: Path, repository_root: Path
) -> None:
    converter = LibreDwgConverter(dwg2dxf_path, repository_root / "data" / "cache" / "converted")
    document = DrawingFileOpener(DxfDocumentLoader(), converter).open(
        pilot_objects_root / MIXED_ENCODING_DRAWING
    )
    fingerprints = EntityFingerprinter().modelspace_fingerprints(document)
    assert len(fingerprints) > 0
