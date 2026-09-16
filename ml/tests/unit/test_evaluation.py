from shapely.geometry import Point

from greenplan.domain.norms import SHRUB, TREE
from greenplan_ml.evaluation import (
    BASELINE_SOURCE,
    MODEL_SOURCE,
    EvaluationReport,
    ObjectEvaluation,
    TargetMetrics,
    matched_count,
    render_markdown,
    totals_of,
)
from greenplan_ml.sample_store import PlantingMeta


def reference(*positions: tuple[float, float]) -> tuple[PlantingMeta, ...]:
    return tuple(PlantingMeta(x, y, TREE, "липа мелколистная") for x, y in positions)


def test_each_reference_tree_is_matched_at_most_once() -> None:
    points = [Point(0.0, 0.0), Point(0.5, 0.0), Point(1.0, 0.0)]
    assert matched_count(points, reference((0.0, 0.0)), 2.0) == 1


def test_points_beyond_the_tolerance_do_not_match() -> None:
    assert matched_count([Point(0.0, 0.0)], reference((5.0, 0.0)), 2.0) == 0
    assert matched_count([Point(0.0, 0.0)], reference((1.5, 0.0)), 2.0) == 1


def test_nearest_reference_wins_when_several_are_in_range() -> None:
    points = [Point(0.0, 0.0), Point(3.0, 0.0)]
    assert matched_count(points, reference((0.2, 0.0), (3.1, 0.0)), 1.0) == 2


def test_empty_input_matches_nothing() -> None:
    assert matched_count([], reference((0.0, 0.0)), 2.0) == 0
    assert matched_count([Point(0.0, 0.0)], (), 2.0) == 0


def test_totals_sum_counts_and_recompute_the_scores() -> None:
    first = TargetMetrics(MODEL_SOURCE, TREE, 2.0, 10, 10, 5, 0.5, 0.5, 0.5)
    second = TargetMetrics(MODEL_SOURCE, TREE, 2.0, 10, 10, 9, 0.9, 0.9, 0.9)
    evaluations = [ObjectEvaluation("a", "A", (first,), 0.0), ObjectEvaluation("b", "A", (second,), 0.0)]
    totals = totals_of(evaluations)
    assert len(totals) == 1
    assert totals[0].expected == 20
    assert totals[0].matched == 14
    assert totals[0].precision == 0.7
    assert totals[0].f1 == 0.7


def test_totals_keep_sources_and_targets_apart() -> None:
    metrics = (
        TargetMetrics(MODEL_SOURCE, TREE, 2.0, 4, 4, 4, 1.0, 1.0, 1.0),
        TargetMetrics(BASELINE_SOURCE, TREE, 2.0, 4, 4, 2, 0.5, 0.5, 0.5),
        TargetMetrics(MODEL_SOURCE, SHRUB, 2.0, 4, 4, 1, 0.25, 0.25, 0.25),
    )
    totals = totals_of([ObjectEvaluation("a", "A", metrics, 0.0)])
    assert {(item.source, item.target) for item in totals} == {
        (MODEL_SOURCE, TREE),
        (BASELINE_SOURCE, TREE),
        (MODEL_SOURCE, SHRUB),
    }


def test_markdown_report_lists_objects_and_totals() -> None:
    metrics = (TargetMetrics(MODEL_SOURCE, TREE, 2.0, 4, 4, 3, 0.75, 0.75, 0.75),)
    evaluation = ObjectEvaluation("olimpiyskaya", "A", metrics, 1.25)
    text = render_markdown(EvaluationReport((evaluation,), totals_of([evaluation])))
    assert "olimpiyskaya" in text
    assert "1.25 м" in text
    assert text.count("| model | tree |") == 2
