import json
from pathlib import Path

from shapely.geometry import Point, box

from greenplan.domain.norms import SHRUB, TREE
from greenplan.domain.site import SiteDiagnostics, SiteModel
from greenplan_ml.dataset_builder import (
    MANIFEST_FILE,
    ObjectReport,
    PilotCatalog,
    inside_share,
    write_manifest,
)
from greenplan_ml.reference_extractor import ReferencePlanting
from greenplan_ml.sample_builder import SampleSettings


def site_with_boundary() -> SiteModel:
    area = box(0.0, 0.0, 100.0, 50.0)
    return SiteModel(area, area, (), (), (), SiteDiagnostics())


def planting_at(x: float, y: float) -> ReferencePlanting:
    return ReferencePlanting(Point(x, y), TREE, "tree", "липа мелколистная", "layer", "scheme")


def test_share_counts_plantings_inside_the_boundary() -> None:
    plantings = [planting_at(10.0, 10.0), planting_at(20.0, 20.0), planting_at(500.0, 500.0)]
    assert inside_share(site_with_boundary(), plantings) == 2 / 3


def test_share_ignores_shrubs_filled_into_outlines_when_blocks_exist() -> None:
    legend = [
        ReferencePlanting(Point(900.0 + index, 900.0), SHRUB, "shrub", "спирея", "layer", "scheme", True)
        for index in range(20)
    ]
    assert inside_share(site_with_boundary(), [planting_at(10.0, 10.0), *legend]) == 1.0
    assert inside_share(site_with_boundary(), legend) == 0.0


def test_share_is_zero_without_plantings() -> None:
    assert inside_share(site_with_boundary(), []) == 0.0


def test_pilot_catalogue_reads_every_object(knowledge_root: Path) -> None:
    catalog = PilotCatalog.from_file(knowledge_root / "dataset" / "pilot_objects.yaml")
    assert len(catalog.objects) == 12
    assert catalog.dataset_root.endswith("Пилотный проект 20 улиц")
    assert all(item.input_path and item.reference_path for item in catalog.objects)


def test_catalogue_filters_objects_by_level(knowledge_root: Path) -> None:
    catalog = PilotCatalog.from_file(knowledge_root / "dataset" / "pilot_objects.yaml")
    selected = catalog.of_levels(["A"])
    assert {item.level for item in selected} == {"A"}
    assert len(selected) < len(catalog.objects)


def test_no_levels_means_every_object(knowledge_root: Path) -> None:
    catalog = PilotCatalog.from_file(knowledge_root / "dataset" / "pilot_objects.yaml")
    assert catalog.of_levels(None) == catalog.objects


def test_selection_narrows_the_level_to_named_objects(knowledge_root: Path) -> None:
    catalog = PilotCatalog.from_file(knowledge_root / "dataset" / "pilot_objects.yaml")
    selected = catalog.selected(["A"], ["bagritskogo"])
    assert [item.object_id for item in selected] == ["bagritskogo"]
    assert catalog.selected(None, None) == catalog.objects


def test_rebuilding_one_object_keeps_the_others_in_the_manifest(tmp_path: Path) -> None:
    settings = SampleSettings()
    write_manifest(
        tmp_path,
        [ObjectReport("first", "A", True, crops=4), ObjectReport("second", "A", True, crops=7)],
        settings,
    )
    write_manifest(tmp_path, [ObjectReport("second", "A", True, crops=9)], settings)
    content = json.loads((tmp_path / MANIFEST_FILE).read_text(encoding="utf-8"))
    by_id = {item["object_id"]: item["crops"] for item in content["objects"]}
    assert by_id == {"first": 4, "second": 9}


def test_manifest_records_built_and_skipped_objects(tmp_path: Path) -> None:
    reports = [
        ObjectReport("first", "A", True, crops=4, trees=10, shrubs=20, inside_boundary_share=0.98),
        ObjectReport("second", "B", False, reason="no_reference_plantings"),
    ]
    path = write_manifest(tmp_path, reports, SampleSettings(crop_size=128, stride=96))
    content = json.loads(path.read_text(encoding="utf-8"))
    assert path.name == MANIFEST_FILE
    assert content["crop_size"] == 128
    assert content["objects"][0]["crops"] == 4
    assert content["objects"][0]["inside_boundary_share"] == 0.98
    assert content["objects"][1]["reason"] == "no_reference_plantings"
