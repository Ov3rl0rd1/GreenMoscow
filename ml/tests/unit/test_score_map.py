from pathlib import Path

import numpy as np
import pytest
import torch

from greenplan.domain.errors import ConfigurationError
from greenplan.domain.norms import TREE
from greenplan.placement.placement_settings import PlacementSettings
from greenplan.placement.raster import RasterGrid, SiteRaster
from greenplan.placement.score_maps import RuleScoreMap
from greenplan_ml.model import HeatmapUNet, UNetSettings
from greenplan_ml.onnx_export import export_onnx, load_checkpoint, save_checkpoint
from greenplan_ml.score_map import ModelScoreMap, ModelScoreSettings
from greenplan_ml.site_loader import SiteLoader
from greenplan_ml.synthetic import SyntheticStreetGenerator

CELL_SIZE_M = 0.5


@pytest.fixture(scope="module")
def model_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    directory = tmp_path_factory.mktemp("score_map")
    torch.manual_seed(0)
    model = HeatmapUNet(UNetSettings(base_channels=4, depth=2))
    checkpoint = load_checkpoint(save_checkpoint(directory / "model.pt", model, CELL_SIZE_M))
    return export_onnx(checkpoint, directory / "model.onnx", sample_size=32)


@pytest.fixture(scope="module")
def street_raster(knowledge_root: Path):
    street = SyntheticStreetGenerator().generate()
    loader = SiteLoader.from_knowledge(knowledge_root, cell_size_m=CELL_SIZE_M)
    return street.site, loader.rasterize(street.site)


def rules() -> RuleScoreMap:
    return RuleScoreMap(PlacementSettings().tree_score)


def test_score_has_the_shape_of_the_raster(model_path: Path, street_raster) -> None:
    site, raster = street_raster
    score = ModelScoreMap.from_file(model_path, rules(), TREE).score(raster, site)
    assert score.shape == raster.grid.shape
    assert score.dtype == np.float32


def test_forbidden_cells_score_zero(model_path: Path, street_raster) -> None:
    site, raster = street_raster
    score = ModelScoreMap.from_file(model_path, rules(), TREE).score(raster, site)
    assert float(score[~raster.allowed].max()) == 0.0
    assert float(score[raster.allowed].max()) > 0.0


def test_rule_weight_of_zero_leaves_only_the_model(model_path: Path, street_raster) -> None:
    site, raster = street_raster
    settings = ModelScoreSettings(model_weight=1.0, rule_weight=0.0)
    score = ModelScoreMap.from_file(model_path, rules(), TREE, settings).score(raster, site)
    baseline = rules().score(raster, site)
    assert not np.allclose(score, baseline)
    assert float(score.max()) <= 1.0


def test_model_weight_of_zero_reproduces_the_rules(model_path: Path, street_raster) -> None:
    site, raster = street_raster
    settings = ModelScoreSettings(model_weight=0.0, rule_weight=1.0)
    score = ModelScoreMap.from_file(model_path, rules(), TREE, settings).score(raster, site)
    assert np.allclose(score, rules().score(raster, site))


def test_cell_size_mismatch_is_refused(model_path: Path, street_raster) -> None:
    site, raster = street_raster
    coarse = SiteRaster(
        grid=RasterGrid(0.0, 0.0, 1.0, raster.grid.rows, raster.grid.columns),
        plantable=raster.plantable,
        allowed=raster.allowed,
        conditional=raster.conditional,
        clearance_m=raster.clearance_m,
        reference_edge_distance_m=raster.reference_edge_distance_m,
    )
    with pytest.raises(ConfigurationError):
        ModelScoreMap.from_file(model_path, rules(), TREE).score(coarse, site)
