import hashlib
import pickle
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Protocol

import greenplan
from greenplan.domain.site import SiteModel

DRAWING_SUFFIXES = {".dwg", ".dxf"}
RECOGNITION_PACKAGES = ("domain", "geometry", "ingest", "recognition")
CACHE_SUFFIX = ".site.pkl"
OUTPUT_DXF_SUFFIX = "_greenplan.dxf"
CHUNK_BYTES = 1 << 20


class Digest(Protocol):
    def update(self, data: bytes, /) -> None: ...


class SiteCache:
    def __init__(self, directory: Path, fingerprint: str) -> None:
        self._directory = directory
        self._fingerprint = fingerprint

    @classmethod
    def for_recognition(cls, directory: Path, knowledge_root: Path, settings: object) -> "SiteCache":
        return cls(directory, recognition_fingerprint(knowledge_root, settings))

    def key(self, input_path: Path, search_root: Path | None, overlays: Sequence[Path] = ()) -> str:
        digest = hashlib.sha256(self._fingerprint.encode("utf-8"))
        for path in drawing_files(input_path, search_root, overlays):
            digest.update(drawing_label(path, search_root).encode("utf-8"))
            update_with_file(digest, path)
        return digest.hexdigest()

    def load(self, key: str) -> SiteModel | None:
        path = self._path(key)
        if not path.is_file():
            return None
        try:
            site = pickle.loads(path.read_bytes())
        except (OSError, pickle.UnpicklingError, EOFError, AttributeError, ImportError):
            return None
        return site if isinstance(site, SiteModel) else None

    def store(self, key: str, site: SiteModel) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        temporary = self._path(key).with_suffix(".tmp")
        temporary.write_bytes(pickle.dumps(site, protocol=pickle.HIGHEST_PROTOCOL))
        temporary.replace(self._path(key))

    def _path(self, key: str) -> Path:
        return self._directory / f"{key}{CACHE_SUFFIX}"


def drawing_files(input_path: Path, search_root: Path | None, overlays: Sequence[Path]) -> list[Path]:
    found = {input_path.resolve(), *(overlay.resolve() for overlay in overlays)}
    if search_root is not None and search_root.is_dir():
        found.update(
            path.resolve()
            for path in search_root.rglob("*")
            if path.is_file()
            and path.suffix.lower() in DRAWING_SUFFIXES
            and not path.name.lower().endswith(OUTPUT_DXF_SUFFIX)
        )
    return sorted(found, key=lambda path: str(path).lower())


def drawing_label(path: Path, search_root: Path | None) -> str:
    if search_root is not None and path.is_relative_to(search_root.resolve()):
        return path.relative_to(search_root.resolve()).as_posix().lower()
    return path.name.lower()


def recognition_fingerprint(knowledge_root: Path, settings: object) -> str:
    digest = hashlib.sha256(f"{greenplan.__version__}|{settings!r}".encode())
    package_root = Path(greenplan.__file__).parent
    sources = sorted(
        path for package in RECOGNITION_PACKAGES for path in (package_root / package).rglob("*.py")
    )
    knowledge = sorted(path for path in knowledge_root.rglob("*") if path.is_file())
    for path in (*sources, *knowledge):
        digest.update(path.name.encode("utf-8"))
        update_with_file(digest, path)
    return digest.hexdigest()


def update_with_file(digest: Digest, path: Path) -> None:
    for chunk in file_chunks(path):
        digest.update(chunk)


def file_chunks(path: Path) -> Iterable[bytes]:
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_BYTES):
            yield chunk
