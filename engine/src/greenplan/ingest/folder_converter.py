import shutil
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from greenplan.domain.errors import ConversionError
from greenplan.ingest.dwg_converter import DwgConverter

DWG_SUFFIX = ".dwg"
DXF_SUFFIX = ".dxf"
IGNORED_PATH_MARKER = "PaxHeader"


@dataclass
class FolderConversion:
    converted: list[Path] = field(default_factory=list)
    copied: list[Path] = field(default_factory=list)
    failed: dict[Path, str] = field(default_factory=dict)


class FolderConverter:
    def __init__(self, converter: DwgConverter) -> None:
        self._converter = converter

    def convert(self, source_root: Path, target_root: Path) -> FolderConversion:
        result = FolderConversion()
        for source in drawings_under(source_root):
            target = mirrored_dxf_path(source, source_root, target_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.suffix.lower() == DXF_SUFFIX:
                shutil.copyfile(source, target)
                result.copied.append(target)
                continue
            self._convert_one(source, target, result)
        return result

    def _convert_one(self, source: Path, target: Path, result: FolderConversion) -> None:
        try:
            shutil.copyfile(self._converter.convert(source), target)
        except ConversionError as error:
            result.failed[source] = str(error)
            return
        result.converted.append(target)


def drawings_under(root: Path) -> Iterator[Path]:
    for path in sorted(root.rglob("*")):
        if (
            path.is_file()
            and path.suffix.lower() in (DWG_SUFFIX, DXF_SUFFIX)
            and IGNORED_PATH_MARKER not in path.parts
        ):
            yield path


def mirrored_dxf_path(source: Path, source_root: Path, target_root: Path) -> Path:
    return (target_root / source.relative_to(source_root)).with_suffix(DXF_SUFFIX)
