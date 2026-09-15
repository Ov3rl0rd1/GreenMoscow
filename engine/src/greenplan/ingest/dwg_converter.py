import re
from pathlib import Path
from typing import Protocol

from greenplan.domain.errors import ConversionError
from greenplan.ingest.command_runner import CommandRunner, SubprocessCommandRunner
from greenplan.ingest.file_digest import sha256_of_file

DIGEST_PREFIX_LENGTH = 16
DEFAULT_TIMEOUT_S = 600
STDERR_TAIL_LENGTH = 500
UNSAFE_FILENAME_CHARACTERS = re.compile(r"[^\w\-.]+")


class DwgConverter(Protocol):
    def convert(self, dwg_path: Path) -> Path: ...


class LibreDwgConverter:
    def __init__(
        self,
        executable: Path,
        cache_directory: Path,
        runner: CommandRunner | None = None,
        timeout_s: int = DEFAULT_TIMEOUT_S,
    ) -> None:
        self._executable = executable
        self._cache_directory = cache_directory
        self._runner = runner or SubprocessCommandRunner()
        self._timeout_s = timeout_s

    def convert(self, dwg_path: Path) -> Path:
        if not dwg_path.is_file():
            raise ConversionError(f"DWG file not found: {dwg_path}")
        target = self.cached_path_for(dwg_path)
        if is_usable_file(target):
            return target
        target.parent.mkdir(parents=True, exist_ok=True)
        self._run_conversion(dwg_path, target)
        return target

    def cached_path_for(self, dwg_path: Path) -> Path:
        digest = sha256_of_file(dwg_path)[:DIGEST_PREFIX_LENGTH]
        safe_stem = UNSAFE_FILENAME_CHARACTERS.sub("_", dwg_path.stem)
        return self._cache_directory / f"{digest}_{safe_stem}.dxf"

    def _run_conversion(self, dwg_path: Path, target: Path) -> None:
        arguments = [str(self._executable), "-y", "-o", str(target), str(dwg_path)]
        result = self._runner.run(arguments, self._timeout_s)
        if result.succeeded and is_usable_file(target):
            return
        target.unlink(missing_ok=True)
        raise ConversionError(f"dwg2dxf failed for {dwg_path}: {result.stderr[-STDERR_TAIL_LENGTH:]}")


def is_usable_file(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0
