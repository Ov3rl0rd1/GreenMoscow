from collections.abc import Sequence
from pathlib import Path

import pytest

from greenplan.domain.errors import ConversionError
from greenplan.ingest.command_runner import CommandResult
from greenplan.ingest.dwg_converter import LibreDwgConverter
from greenplan.ingest.executable_locator import (
    DWG2DXF_ENVIRONMENT_VARIABLE,
    Dwg2DxfLocator,
    dwg2dxf_binary_name,
)


class RecordingRunner:
    def __init__(self, writes_output: bool = True, return_code: int = 0) -> None:
        self.calls: list[list[str]] = []
        self._writes_output = writes_output
        self._return_code = return_code

    def run(self, arguments: Sequence[str], timeout_s: int) -> CommandResult:
        self.calls.append(list(arguments))
        if self._writes_output:
            Path(arguments[3]).write_text("0\nEOF\n", encoding="utf-8")
        return CommandResult(self._return_code, "", "conversion failed")


def make_dwg(directory: Path, name: str = "tile.dwg", content: bytes = b"AC1032-content") -> Path:
    path = directory / name
    path.write_bytes(content)
    return path


def test_conversion_result_is_cached_by_content(tmp_path: Path) -> None:
    runner = RecordingRunner()
    converter = LibreDwgConverter(Path("dwg2dxf"), tmp_path / "cache", runner)
    source = make_dwg(tmp_path)
    first = converter.convert(source)
    second = converter.convert(source)
    assert first == second
    assert first.is_file()
    assert len(runner.calls) == 1


def test_changed_content_is_converted_again(tmp_path: Path) -> None:
    runner = RecordingRunner()
    converter = LibreDwgConverter(Path("dwg2dxf"), tmp_path / "cache", runner)
    source = make_dwg(tmp_path)
    converter.convert(source)
    source.write_bytes(b"AC1032-changed")
    converter.convert(source)
    assert len(runner.calls) == 2


def test_failed_conversion_raises_and_leaves_no_partial_file(tmp_path: Path) -> None:
    runner = RecordingRunner(writes_output=True, return_code=1)
    converter = LibreDwgConverter(Path("dwg2dxf"), tmp_path / "cache", runner)
    source = make_dwg(tmp_path)
    with pytest.raises(ConversionError):
        converter.convert(source)
    assert not converter.cached_path_for(source).exists()


def test_missing_source_raises(tmp_path: Path) -> None:
    converter = LibreDwgConverter(Path("dwg2dxf"), tmp_path / "cache", RecordingRunner())
    with pytest.raises(ConversionError):
        converter.convert(tmp_path / "absent.dwg")


def test_cached_name_is_safe_for_bracketed_tile_names(tmp_path: Path) -> None:
    converter = LibreDwgConverter(Path("dwg2dxf"), tmp_path / "cache", RecordingRunner())
    source = make_dwg(tmp_path, "output[1-7]_3_ДЖКХ-25_05352up.dwg")
    assert "[" not in converter.cached_path_for(source).name


def test_locator_prefers_environment_variable(tmp_path: Path) -> None:
    configured = tmp_path / "custom-dwg2dxf"
    configured.write_text("", encoding="utf-8")
    locator = Dwg2DxfLocator([], environment={DWG2DXF_ENVIRONMENT_VARIABLE: str(configured)})
    assert locator.locate() == configured


def test_locator_finds_binary_in_search_directory(tmp_path: Path) -> None:
    bundled = tmp_path / dwg2dxf_binary_name()
    bundled.write_text("", encoding="utf-8")
    assert Dwg2DxfLocator([tmp_path], environment={}).locate() == bundled
