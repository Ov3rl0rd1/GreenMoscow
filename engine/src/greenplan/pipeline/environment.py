import importlib.util
import os
from datetime import UTC, datetime
from pathlib import Path

from greenplan.domain.errors import ConfigurationError
from greenplan.ingest.executable_locator import Dwg2DxfLocator

KNOWLEDGE_ROOT_VARIABLE = "GREENPLAN_KNOWLEDGE_ROOT"
CACHE_DIRECTORY_VARIABLE = "GREENPLAN_CACHE_DIR"
JOBS_ROOT_VARIABLE = "GREENPLAN_JOBS_ROOT"
MODEL_VARIABLE = "GREENPLAN_MODEL"
MODEL_RUNTIME_PACKAGE = "greenplan_ml"
BUNDLED_MODEL = Path("models") / "greenplan-guidance.onnx"
KNOWLEDGE_DIRECTORY_NAME = "knowledge"
NORMS_MARKER = Path("rules") / "norms.yaml"
BUNDLED_CONVERTER_DIRECTORY = Path("tools") / "bin" / "libredwg"
DEFAULT_CACHE_DIRECTORY = Path("data") / "cache" / "converted"
DEFAULT_JOBS_DIRECTORY = "jobs"


def locate_knowledge_root(explicit: Path | None = None) -> Path:
    candidates = (
        [explicit]
        if explicit is not None
        else [
            _from_environment(KNOWLEDGE_ROOT_VARIABLE),
            *_ancestor_knowledge_directories(),
            _cwd_knowledge(),
        ]
    )
    for candidate in candidates:
        if candidate is not None and (candidate / NORMS_MARKER).is_file():
            return candidate
    raise ConfigurationError(
        f"knowledge directory with {NORMS_MARKER} not found; set {KNOWLEDGE_ROOT_VARIABLE}"
    )


def locate_dwg2dxf(explicit: Path | None, knowledge_root: Path) -> Path | None:
    if explicit is None:
        return Dwg2DxfLocator([knowledge_root.parent / BUNDLED_CONVERTER_DIRECTORY]).locate()
    if not explicit.is_file():
        raise ConfigurationError(f"dwg2dxf executable not found: {explicit}")
    return explicit


def locate_model(explicit: Path | None, knowledge_root: Path) -> Path | None:
    configured = explicit or _from_environment(MODEL_VARIABLE)
    if configured is not None:
        if not configured.is_file():
            raise ConfigurationError(f"model file not found: {configured}")
        return configured
    bundled = knowledge_root.parent / BUNDLED_MODEL
    if bundled.is_file() and importlib.util.find_spec(MODEL_RUNTIME_PACKAGE) is not None:
        return bundled
    return None


def resolve_cache_directory(explicit: Path | None, knowledge_root: Path) -> Path:
    return (
        explicit
        or _from_environment(CACHE_DIRECTORY_VARIABLE)
        or knowledge_root.parent / DEFAULT_CACHE_DIRECTORY
    )


def resolve_jobs_root(explicit: Path | None) -> Path:
    return explicit or _from_environment(JOBS_ROOT_VARIABLE) or Path.cwd() / DEFAULT_JOBS_DIRECTORY


def current_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _from_environment(variable: str) -> Path | None:
    value = os.environ.get(variable)
    return Path(value) if value else None


def _ancestor_knowledge_directories() -> list[Path]:
    return [ancestor / KNOWLEDGE_DIRECTORY_NAME for ancestor in Path(__file__).resolve().parents]


def _cwd_knowledge() -> Path:
    return Path.cwd() / KNOWLEDGE_DIRECTORY_NAME
