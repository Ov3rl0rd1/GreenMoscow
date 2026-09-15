from collections import defaultdict
from pathlib import Path, PureWindowsPath

DRAWING_SUFFIXES = (".dwg", ".dxf")
IGNORED_DIRECTORY_PREFIXES = ("PaxHeader",)


class XrefFileLocator:
    def __init__(self, search_root: Path) -> None:
        self._search_root = search_root
        self._files_by_name = self._index_drawing_files(search_root)

    def locate(self, declared_path: str, referencing_directory: Path) -> Path | None:
        declared = PureWindowsPath(declared_path.strip())
        if not declared.name:
            return None
        return self._direct_match(declared, referencing_directory) or self._closest_by_name(
            declared.name, referencing_directory
        )

    def _direct_match(self, declared: PureWindowsPath, referencing_directory: Path) -> Path | None:
        if declared.is_absolute():
            candidate = Path(str(declared))
        else:
            candidate = referencing_directory.joinpath(*[part for part in declared.parts if part != "."])
        return candidate if candidate.is_file() else None

    def _closest_by_name(self, file_name: str, referencing_directory: Path) -> Path | None:
        candidates = self._candidates_for(file_name)
        if not candidates:
            return None
        return max(candidates, key=lambda candidate: self._closeness(candidate, referencing_directory))

    def _candidates_for(self, file_name: str) -> list[Path]:
        stem = PureWindowsPath(file_name).stem.lower()
        return [path for suffix in DRAWING_SUFFIXES for path in self._files_by_name.get(stem + suffix, [])]

    def _closeness(self, candidate: Path, referencing_directory: Path) -> tuple[int, int]:
        shared_parts = 0
        for candidate_part, directory_part in zip(
            candidate.parent.parts, referencing_directory.parts, strict=False
        ):
            if candidate_part.lower() != directory_part.lower():
                break
            shared_parts += 1
        return shared_parts, -len(candidate.parts)

    def _index_drawing_files(self, search_root: Path) -> dict[str, list[Path]]:
        index: dict[str, list[Path]] = defaultdict(list)
        if not search_root.is_dir():
            return index
        for path in search_root.rglob("*"):
            if self._is_indexable(path):
                index[path.name.lower()].append(path)
        return index

    def _is_indexable(self, path: Path) -> bool:
        return (
            path.suffix.lower() in DRAWING_SUFFIXES
            and path.is_file()
            and not any(part.startswith(IGNORED_DIRECTORY_PREFIXES) for part in path.parts)
        )
