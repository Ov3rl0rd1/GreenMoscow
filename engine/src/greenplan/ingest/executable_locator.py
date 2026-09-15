import os
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path

DWG2DXF_ENVIRONMENT_VARIABLE = "GREENPLAN_DWG2DXF"


def dwg2dxf_binary_name() -> str:
    return "dwg2dxf.exe" if os.name == "nt" else "dwg2dxf"


class Dwg2DxfLocator:
    def __init__(
        self, search_directories: Sequence[Path], environment: Mapping[str, str] | None = None
    ) -> None:
        self._search_directories = tuple(search_directories)
        self._environment = environment if environment is not None else os.environ

    def locate(self) -> Path | None:
        return self._from_environment() or self._from_search_directories() or self._from_system_path()

    def _from_environment(self) -> Path | None:
        configured = self._environment.get(DWG2DXF_ENVIRONMENT_VARIABLE)
        return Path(configured) if configured and Path(configured).is_file() else None

    def _from_search_directories(self) -> Path | None:
        candidates = (directory / dwg2dxf_binary_name() for directory in self._search_directories)
        return next((candidate for candidate in candidates if candidate.is_file()), None)

    def _from_system_path(self) -> Path | None:
        located = shutil.which(dwg2dxf_binary_name())
        return Path(located) if located else None
