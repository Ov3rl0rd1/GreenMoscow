from pathlib import Path

import pytest

from greenplan.explain.report_model import PlantingReport
from greenplan.explain.report_writers import MARKDOWN_REPORT_NAME, ReportWriterSet

from fixtures.explanation_checks import citations_violating_policy, unexplained_numbers

pytestmark = [pytest.mark.realdata, pytest.mark.converter, pytest.mark.slow]


def test_report_explains_every_plant_and_rejection(bagritskogo_report: PlantingReport) -> None:
    explanations = (*bagritskogo_report.plants, *bagritskogo_report.rejections)
    assert bagritskogo_report.summary.trees > 20
    assert all(explanation.explanation_ru for explanation in explanations)
    assert all(unexplained_numbers(explanation) == set() for explanation in explanations)


def test_report_never_shows_locators_of_unverified_citations(bagritskogo_report: PlantingReport) -> None:
    assert citations_violating_policy(bagritskogo_report) == []


def test_report_files_are_written(bagritskogo_report: PlantingReport, tmp_path: Path) -> None:
    paths = ReportWriterSet.default().write_all(bagritskogo_report, tmp_path)
    assert all(path.stat().st_size > 0 for path in paths.values())
    assert "## Основные причины отказов" in paths[MARKDOWN_REPORT_NAME].read_text(encoding="utf-8")
