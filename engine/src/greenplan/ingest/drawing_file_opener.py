from pathlib import Path

import ezdxf
from ezdxf import recover
from ezdxf.document import Drawing

from greenplan.domain.errors import DrawingLoadError
from greenplan.ingest.dwg_converter import DwgConverter

DWG_SUFFIX = ".dwg"
DXF_SUFFIX = ".dxf"


class DxfDocumentLoader:
    def load(self, path: Path) -> Drawing:
        try:
            document, _auditor = recover.readfile(str(path))
        except (OSError, ezdxf.DXFStructureError) as error:
            raise DrawingLoadError(f"cannot read DXF {path}: {error}") from error
        return document


class DrawingFileOpener:
    def __init__(self, loader: DxfDocumentLoader, converter: DwgConverter | None) -> None:
        self._loader = loader
        self._converter = converter

    def open(self, path: Path) -> Drawing:
        return self._loader.load(self.resolve_dxf_path(path))

    def resolve_dxf_path(self, path: Path) -> Path:
        suffix = path.suffix.lower()
        if suffix == DXF_SUFFIX:
            return path
        if suffix != DWG_SUFFIX:
            raise DrawingLoadError(f"unsupported drawing format: {path}")
        if self._converter is None:
            raise DrawingLoadError(f"DWG input requires a converter: {path}")
        return self._converter.convert(path)
