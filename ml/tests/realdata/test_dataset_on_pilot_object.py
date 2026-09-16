from pathlib import Path

import numpy as np
import pytest

from greenplan.domain.norms import SHRUB, TREE
from greenplan_ml.dataset_builder import DatasetBuilder, ObjectReport, PilotCatalog
from greenplan_ml.feature_channels import CHANNEL_COUNT, PLANTABLE_CHANNEL_INDEX
from greenplan_ml.sample_builder import SampleSettings
from greenplan_ml.sample_store import read_object
from greenplan_ml.targets import TARGET_CHANNEL_COUNT, TREE_CHANNEL_INDEX

pytestmark = [pytest.mark.realdata, pytest.mark.slow]

OBJECT_ID = "bagritskogo"
CROP_SIZE = 256


@pytest.fixture(scope="module")
def built(
    tmp_path_factory: pytest.TempPathFactory,
    knowledge_root: Path,
    pilot_objects_root: Path,
    dwg2dxf_path: Path,
    dxf_cache_root: Path,
) -> tuple[ObjectReport, Path]:
    catalog = PilotCatalog.from_file(knowledge_root / "dataset" / "pilot_objects.yaml")
    item = next(entry for entry in catalog.objects if entry.object_id == OBJECT_ID)
    builder = DatasetBuilder.from_knowledge(
        knowledge_root,
        dwg2dxf_path,
        dxf_cache_root,
        samples=SampleSettings(crop_size=CROP_SIZE, stride=CROP_SIZE - 64),
    )
    output = tmp_path_factory.mktemp("dataset")
    report = builder.build_object(item, pilot_objects_root, output)
    return report, output / OBJECT_ID


def test_reference_plantings_are_found_in_the_project_drawing(built) -> None:
    report, _directory = built
    assert report.is_built, report.reason
    assert report.trees > 0
    assert report.shrubs > 0
    assert report.scheme_id


def test_reference_lies_in_the_same_coordinates_as_the_base_drawing(built) -> None:
    report, _directory = built
    assert report.inside_boundary_share > 0.8


def test_stored_stacks_match_the_declared_grid(built) -> None:
    _report, directory = built
    stored = read_object(directory)
    rows, columns = stored.features.shape[1], stored.features.shape[2]
    assert stored.features.shape[0] == CHANNEL_COUNT
    assert stored.targets.shape == (TARGET_CHANNEL_COUNT, rows, columns)
    assert stored.masks.shape == (2, rows, columns)
    assert rows >= CROP_SIZE and columns >= CROP_SIZE


def test_every_crop_holds_plantable_cells(built) -> None:
    _report, directory = built
    stored = read_object(directory)
    assert stored.meta.crops
    for window in stored.meta.crops[:20]:
        features, _targets = stored.crop(window)
        assert features[PLANTABLE_CHANNEL_INDEX].mean() > 0.0


def test_tree_heatmap_peaks_at_reference_positions(built) -> None:
    _report, directory = built
    stored = read_object(directory)
    peak = float(np.asarray(stored.targets[TREE_CHANNEL_INDEX], dtype=np.float32).max())
    assert peak == pytest.approx(1.0, abs=0.05)


def test_metadata_lists_every_extracted_planting(built) -> None:
    report, directory = built
    meta = read_object(directory).meta
    assert len(meta.plantings) == report.trees + report.shrubs
    assert len(meta.plantings_of(TREE)) == report.trees
    assert len(meta.plantings_of(SHRUB)) == report.shrubs


def test_feature_channels_stay_in_the_normalised_range(built) -> None:
    _report, directory = built
    stored = read_object(directory)
    sample = np.asarray(stored.features[:, :CROP_SIZE, :CROP_SIZE], dtype=np.float32)
    assert np.isfinite(sample).all()
    assert sample.min() >= 0.0
    assert sample.max() <= 1.0
