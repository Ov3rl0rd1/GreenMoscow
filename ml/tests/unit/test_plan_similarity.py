import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from greenplan.domain.norms import SHRUB, TREE
from greenplan_ml.plan_similarity import (
    SimilarityMetrics,
    chamfer,
    f1_score,
    grouped_share,
    matched_pairs,
    median_spacing,
    planned_positions,
    similarity_markdown,
)

REFERENCE = np.array([[0.0, 0.0], [10.0, 0.0], [20.0, 0.0]])


def test_each_reference_planting_is_matched_at_most_once() -> None:
    planned = np.array([[0.5, 0.0], [0.7, 0.0], [19.0, 0.0], [50.0, 0.0]])
    assert matched_pairs(planned, REFERENCE, 3.0) == 2
    assert matched_pairs(planned, REFERENCE, 0.6) == 1
    assert matched_pairs(np.empty((0, 2)), REFERENCE, 3.0) == 0


def test_f1_balances_precision_and_recall() -> None:
    assert f1_score(2, 4, 2) == pytest.approx(2 * 0.5 * 1.0 / 1.5, abs=1e-4)
    assert f1_score(0, 0, 5) == 0.0


def test_chamfer_is_zero_for_identical_plans_and_grows_with_offset() -> None:
    assert chamfer(REFERENCE, REFERENCE) == 0.0
    assert chamfer(REFERENCE + [0.0, 2.0], REFERENCE) == pytest.approx(2.0)


def test_spacing_and_grouping_describe_the_arrangement() -> None:
    hedge = np.array([[x, 0.0] for x in np.arange(0.0, 5.0, 1.0)])
    scattered = np.array([[x, 0.0] for x in np.arange(0.0, 50.0, 10.0)])
    assert median_spacing(hedge) == pytest.approx(1.0)
    assert grouped_share(hedge, 1.6) > 0.5
    assert grouped_share(scattered, 1.6) == 0.0


def test_planned_positions_skip_rejected_candidates(tmp_path: Path) -> None:
    report = tmp_path / "planting_report.json"
    plants = [
        {"plant_type": TREE, "status": "accepted", "x": 1.0, "y": 2.0},
        {"plant_type": TREE, "status": "rejected", "x": 5.0, "y": 5.0},
        {"plant_type": SHRUB, "status": "conditionally_accepted", "x": 3.0, "y": 4.0},
    ]
    report.write_text(json.dumps({"plants": plants}), encoding="utf-8")
    assert planned_positions(report, TREE).tolist() == [[1.0, 2.0]]
    assert planned_positions(report, SHRUB).tolist() == [[3.0, 4.0]]


def test_markdown_lists_every_run() -> None:
    row = SimilarityMetrics("kharkovskaya", "model", TREE, 10, 8, 0.8, {"3": 0.5}, 4.2, 6.0, 7.5, 0.3, 0.2)
    text = similarity_markdown([row, replace(row, source="rules")])
    assert "| kharkovskaya | model | tree |" in text
    assert "| kharkovskaya | rules | tree |" in text
