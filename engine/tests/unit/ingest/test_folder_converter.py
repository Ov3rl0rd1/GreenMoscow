from pathlib import Path

from greenplan.domain.errors import ConversionError
from greenplan.ingest.folder_converter import FolderConverter, mirrored_dxf_path


class FakeConverter:
    def __init__(self, cache: Path) -> None:
        self._cache = cache
        self.calls: list[Path] = []

    def convert(self, dwg_path: Path) -> Path:
        self.calls.append(dwg_path)
        if "broken" in dwg_path.stem:
            raise ConversionError(f"cannot convert {dwg_path.name}")
        self._cache.mkdir(parents=True, exist_ok=True)
        target = self._cache / f"{dwg_path.stem}.dxf"
        target.write_text(f"converted {dwg_path.name}", encoding="utf-8")
        return target


def object_folder(root: Path) -> Path:
    (root / "ссылки").mkdir(parents=True)
    (root / "ГП.dwg").write_bytes(b"AC1032")
    (root / "ссылки" / "Борт.dwg").write_bytes(b"AC1032")
    (root / "ссылки" / "Ось.dxf").write_text("0\nEOF", encoding="utf-8")
    (root / "ссылки" / "broken.dwg").write_bytes(b"AC1032")
    (root / "notes.txt").write_text("ignore", encoding="utf-8")
    return root


def test_folder_structure_is_mirrored_with_dxf_files(tmp_path: Path) -> None:
    source = object_folder(tmp_path / "source")
    result = FolderConverter(FakeConverter(tmp_path / "cache")).convert(source, tmp_path / "target")
    assert (tmp_path / "target" / "ГП.dxf").read_text(encoding="utf-8") == "converted ГП.dwg"
    assert (tmp_path / "target" / "ссылки" / "Борт.dxf").is_file()
    assert (tmp_path / "target" / "ссылки" / "Ось.dxf").read_text(encoding="utf-8") == "0\nEOF"
    assert not (tmp_path / "target" / "notes.txt").exists()
    assert len(result.converted) == 2
    assert len(result.copied) == 1


def test_failed_conversions_are_collected_not_raised(tmp_path: Path) -> None:
    source = object_folder(tmp_path / "source")
    result = FolderConverter(FakeConverter(tmp_path / "cache")).convert(source, tmp_path / "target")
    assert list(result.failed) == [source / "ссылки" / "broken.dwg"]
    assert not (tmp_path / "target" / "ссылки" / "broken.dxf").exists()


def test_mirrored_path_keeps_relative_folders() -> None:
    target = mirrored_dxf_path(Path("/src/a/b/Файл.DWG"), Path("/src"), Path("/out"))
    assert target == Path("/out/a/b/Файл.dxf")
