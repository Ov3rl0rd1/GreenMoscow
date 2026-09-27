from pathlib import Path

from shapely.geometry import box

from greenplan.domain.site import SiteDiagnostics, SiteModel
from greenplan.pipeline.site_cache import SiteCache

LAWN = box(0.0, 0.0, 30.0, 10.0)


def object_folder(root: Path, main_text: str = "main") -> Path:
    (root / "base").mkdir(parents=True)
    (root / "base" / "main.dxf").write_text(main_text, encoding="utf-8")
    (root / "base" / "tile.DWG").write_text("tile", encoding="utf-8")
    (root / "notes.txt").write_text("не чертёж", encoding="utf-8")
    return root / "base" / "main.dxf"


def site() -> SiteModel:
    return SiteModel(LAWN, LAWN, (), (), (), SiteDiagnostics())


def test_key_depends_on_drawing_content_not_on_the_job_folder(tmp_path: Path) -> None:
    cache = SiteCache(tmp_path / "cache", "fingerprint")
    first = object_folder(tmp_path / "job-1")
    second = object_folder(tmp_path / "job-2")
    changed = object_folder(tmp_path / "job-3", "main changed")
    assert cache.key(first, tmp_path / "job-1") == cache.key(second, tmp_path / "job-2")
    assert cache.key(first, tmp_path / "job-1") != cache.key(changed, tmp_path / "job-3")
    (tmp_path / "job-2" / "notes.txt").write_text("другое", encoding="utf-8")
    assert cache.key(first, tmp_path / "job-1") == cache.key(second, tmp_path / "job-2")


def test_key_changes_with_the_recognition_fingerprint(tmp_path: Path) -> None:
    main = object_folder(tmp_path / "job")
    assert SiteCache(tmp_path, "a").key(main, tmp_path / "job") != SiteCache(tmp_path, "b").key(
        main, tmp_path / "job"
    )


def test_stored_site_is_loaded_and_a_damaged_file_is_ignored(tmp_path: Path) -> None:
    cache = SiteCache(tmp_path / "cache", "fingerprint")
    assert cache.load("missing") is None
    cache.store("key", site())
    loaded = cache.load("key")
    assert loaded is not None and loaded.plantable_surface.equals(LAWN)
    (tmp_path / "cache" / "key.site.pkl").write_bytes(b"not a pickle")
    assert cache.load("key") is None
