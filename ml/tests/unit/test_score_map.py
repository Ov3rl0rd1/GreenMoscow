from pathlib import Path

import numpy as np
import pytest
import torch

from greenplan.domain.errors import ConfigurationError
from greenplan.domain.norms import SHRUB, TREE
from greenplan.placement.placement_settings import PlacementSettings
from greenplan.placement.raster import RasterGrid, SiteRaster
from greenplan.placement.score_maps import MODEL_GUIDANCE, RuleScoreMap
from greenplan_ml.model import HeatmapUNet, UNetSettings
from greenplan_ml.onnx_export import export_onnx, load_checkpoint, save_checkpoint
from greenplan_ml.score_map import ModelScoreMap, ModelScoreSettings, model_guidance, peak_mass
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


def test_guidance_limits_candidates_to_confident_cells(model_path: Path, street_raster) -> None:
    site, raster = street_raster
    loose = ModelScoreMap.from_file(model_path, rules(), TREE, ModelScoreSettings(candidate_threshold=-1.0))
    strict = ModelScoreMap.from_file(model_path, rules(), TREE, ModelScoreSettings(candidate_threshold=2.0))
    assert loose.guide(raster, site).candidates.all()
    assert not strict.guide(raster, site).candidates.any()
    assert loose.guide(raster, site).source == MODEL_GUIDANCE


def test_expected_count_is_the_heat_mass_per_planting(model_path: Path, street_raster) -> None:
    site, raster = street_raster
    guidance = ModelScoreMap.from_file(model_path, rules(), TREE).guide(raster, site)
    doubled = ModelScoreMap.from_file(model_path, rules(), TREE, ModelScoreSettings(count_scale=2.0))
    assert guidance.expected_count >= 0
    assert abs(doubled.guide(raster, site).expected_count - 2 * guidance.expected_count) <= 1


def test_peak_mass_matches_a_unit_gaussian_peak() -> None:
    assert peak_mass(2.0) == pytest.approx(8.0 * np.pi)


def test_model_guidance_serves_trees_and_shrubs_from_one_model(model_path: Path, street_raster) -> None:
    site, raster = street_raster
    maps = model_guidance(model_path)(PlacementSettings())
    tree = maps.tree.guide(raster, site)
    shrub = maps.shrub.guide(raster, site)
    assert tree.score.shape == shrub.score.shape == raster.grid.shape
    assert {tree.source, shrub.source} == {MODEL_GUIDANCE}
    assert SHRUB != TREE


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
