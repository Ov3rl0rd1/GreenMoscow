import os
import shutil
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PILOT_OBJECTS_ROOT = REPOSITORY_ROOT / "data" / "pilot" / "Пилотный проект 20 улиц"
DXF_CACHE_ROOT = REPOSITORY_ROOT / "data" / "cache" / "dxf"


def locate_dwg2dxf() -> Path | None:
    configured = os.environ.get("GREENPLAN_DWG2DXF")
    if configured and Path(configured).is_file():
        return Path(configured)
    bundled = REPOSITORY_ROOT / "tools" / "bin" / "libredwg" / ("dwg2dxf.exe" if os.name == "nt" else "dwg2dxf")
    if bundled.is_file():
        return bundled
    on_path = shutil.which("dwg2dxf")
    return Path(on_path) if on_path else None


@pytest.fixture(scope="session")
def repository_root() -> Path:
    return REPOSITORY_ROOT


@pytest.fixture(scope="session")
def knowledge_root() -> Path:
    return REPOSITORY_ROOT / "knowledge"


@pytest.fixture(scope="session")
def pilot_objects_root() -> Path:
    if not PILOT_OBJECTS_ROOT.is_dir():
        pytest.skip("pilot dataset is not extracted")
    return PILOT_OBJECTS_ROOT


@pytest.fixture(scope="session")
def dxf_cache_root() -> Path:
    return DXF_CACHE_ROOT


@pytest.fixture(scope="session")
def dwg2dxf_path() -> Path:
    located = locate_dwg2dxf()
    if located is None:
        pytest.skip("dwg2dxf binary is not available")
    return located
