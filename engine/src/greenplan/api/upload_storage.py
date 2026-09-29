import io
import zipfile
from pathlib import Path

from greenplan.domain.errors import InvalidUploadError
from greenplan.ingest.input_selection import choose_main, prefer_dxf

DRAWING_SUFFIXES = frozenset({".dxf", ".dwg"})
ARCHIVE_SUFFIX = ".zip"
ZIP_UTF8_FLAG = 0x800
LEGACY_ZIP_ENCODING = "cp437"
RUSSIAN_DOS_ENCODING = "cp866"
IGNORED_PATH_MARKER = "PaxHeader"


class UploadStorage:
    def store(self, directory: Path, file_name: str, content: bytes) -> list[Path]:
        suffix = Path(file_name).suffix.lower()
        if suffix in DRAWING_SUFFIXES:
            path = directory / Path(file_name).name
            path.write_bytes(content)
            return [path]
        if suffix == ARCHIVE_SUFFIX:
            self._extract(directory, content)
            return drawings_in(directory)
        raise InvalidUploadError(f"unsupported upload type '{suffix}': expected .dxf, .dwg or .zip")

    def resolve_main(self, directory: Path, drawings: list[Path], main_file: str | None) -> Path:
        if main_file:
            candidate = given_main(directory, drawings, main_file)
            if candidate.suffix.lower() not in DRAWING_SUFFIXES:
                raise InvalidUploadError(f"main_file must be a .dxf or .dwg drawing: {main_file}")
            return candidate
        if not drawings:
            raise InvalidUploadError("the upload contains no .dxf or .dwg drawings")
        return choose_main(prefer_dxf(drawings))

    def _extract(self, directory: Path, content: bytes) -> None:
        root = directory.resolve()
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                for member in archive.infolist():
                    if member.is_dir():
                        continue
                    target = (root / member_name(member)).resolve()
                    if not target.is_relative_to(root):
                        raise InvalidUploadError(f"unsafe path in archive: {member.filename}")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(member))
        except zipfile.BadZipFile as error:
            raise InvalidUploadError(f"broken zip archive: {error}") from error


def given_main(directory: Path, drawings: list[Path], main_file: str) -> Path:
    candidate = (directory / main_file).resolve()
    if not candidate.is_relative_to(directory.resolve()):
        raise InvalidUploadError(f"main_file not found in upload: {main_file}")
    if candidate.is_file():
        return candidate
    name = Path(main_file).name.casefold()
    named = [path for path in drawings if path.name.casefold() == name]
    if len(named) == 1:
        return named[0].resolve()
    raise InvalidUploadError(f"main_file not found in upload: {main_file}")


def is_archive(file_name: str) -> bool:
    return Path(file_name).suffix.lower() == ARCHIVE_SUFFIX


def member_name(member: zipfile.ZipInfo) -> str:
    if member.flag_bits & ZIP_UTF8_FLAG:
        return member.filename
    try:
        return member.filename.encode(LEGACY_ZIP_ENCODING).decode(RUSSIAN_DOS_ENCODING)
    except UnicodeError:
        return member.filename


def drawings_in(directory: Path) -> list[Path]:
    return sorted(
        path
        for path in directory.rglob("*")
        if path.is_file()
        and path.suffix.lower() in DRAWING_SUFFIXES
        and IGNORED_PATH_MARKER not in path.parts
    )
