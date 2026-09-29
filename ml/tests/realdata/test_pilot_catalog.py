from pathlib import Path

import pytest

from greenplan_ml.dataset_builder import PilotCatalog

pytestmark = pytest.mark.realdata


def catalog_of(knowledge_root: Path) -> PilotCatalog:
    return PilotCatalog.from_file(knowledge_root / "dataset" / "pilot_objects.yaml")


def test_every_listed_drawing_exists(knowledge_root: Path, pilot_objects_root: Path) -> None:
    catalog = catalog_of(knowledge_root)
    missing = [
        f"{item.object_id}: {path}"
        for item in catalog.objects
        for path in (item.input_path, item.reference_path)
        if path is not None and not (pilot_objects_root / path).is_file()
    ]
    assert missing == []


def test_declared_dataset_root_matches_the_extracted_one(
    knowledge_root: Path, pilot_objects_root: Path
) -> None:
    catalog = catalog_of(knowledge_root)
    assert pilot_objects_root.name == Path(catalog.dataset_root).name


def test_level_a_objects_declare_their_layer_scheme(knowledge_root: Path) -> None:
    for item in catalog_of(knowledge_root).of_levels(["A"]):
        assert item.layer_scheme, item.object_id
