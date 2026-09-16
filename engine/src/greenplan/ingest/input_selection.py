import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from greenplan.domain.errors import InvalidInputError

DRAWING_SUFFIXES = frozenset({".dxf", ".dwg"})
PREFERRED_SUFFIX = ".dxf"
TILE_NAME = re.compile(r"(^output\[)|((tp|up|kl|pp|brd)$)", re.IGNORECASE)
MAIN_NAME_HINTS = (
    re.compile(r"генплан", re.IGNORECASE),
    re.compile(r"(^|[\s_\-])гп([\s_\-.]|$)", re.IGNORECASE),
    re.compile(r"апот", re.IGNORECASE),
    re.compile(r"standard", re.IGNORECASE),
    re.compile(r"благоустр", re.IGNORECASE),
)
IGNORED_PATH_MARKER = "PaxHeader"


@dataclass(frozen=True, slots=True)
class DrawingInputs:
    main: Path
    overlays: tuple[Path, ...]
    search_root: Path


class DrawingInputSelector:
    def select(self, paths: Sequence[Path], main: Path | None = None) -> DrawingInputs:
        candidates = self._candidates(paths)
        if not candidates:
            raise InvalidInputError("не найдено ни одного чертежа .dxf или .dwg")
        chosen = self._main(candidates, main)
        overlays = tuple(path for path in candidates if path != chosen)
        return DrawingInputs(chosen, overlays, search_root_of(paths, chosen))

    def _candidates(self, paths: Sequence[Path]) -> list[Path]:
        found: list[Path] = []
        for path in paths:
            found.extend(drawings_in_directory(path) if path.is_dir() else [path])
        missing = [str(path) for path in found if not path.is_file()]
        if missing:
            raise InvalidInputError(f"файл не найден: {', '.join(missing)}")
        return prefer_dxf(unique_paths(found))

    def _main(self, candidates: Sequence[Path], main: Path | None) -> Path:
        if main is not None:
            resolved = main.resolve()
            matching = [path for path in candidates if path.resolve() == resolved]
            if not matching and not main.is_file():
                raise InvalidInputError(f"главный чертёж не найден: {main}")
            return matching[0] if matching else main
        return choose_main(candidates)


def choose_main(candidates: Sequence[Path]) -> Path:
    return max(candidates, key=main_likelihood)


def main_likelihood(path: Path) -> tuple[int, int, int]:
    stem = path.stem
    is_tile = 1 if TILE_NAME.search(stem) else 0
    hints = sum(1 for hint in MAIN_NAME_HINTS if hint.search(stem))
    return -is_tile, hints, path.stat().st_size


def drawings_in_directory(directory: Path) -> list[Path]:
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in DRAWING_SUFFIXES and IGNORED_PATH_MARKER not in path.name
    )


def unique_paths(paths: Sequence[Path]) -> list[Path]:
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        key = path.resolve()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def prefer_dxf(paths: Sequence[Path]) -> list[Path]:
    dxf_stems = {(path.parent.resolve(), path.stem.lower()) for path in paths if is_dxf(path)}
    return [
        path
        for path in paths
        if is_dxf(path) or (path.parent.resolve(), path.stem.lower()) not in dxf_stems
    ]


def is_dxf(path: Path) -> bool:
    return path.suffix.lower() == PREFERRED_SUFFIX


def search_root_of(paths: Sequence[Path], main: Path) -> Path:
    directories = [path for path in paths if path.is_dir()]
    return directories[0] if len(directories) == 1 else main.parent
