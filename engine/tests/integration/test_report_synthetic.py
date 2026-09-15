import csv
import json
from pathlib import Path

import pytest

from greenplan.explain.report_builder import ReportBuilder
from greenplan.explain.report_model import PlantingReport
from greenplan.explain.report_writers import (
    CSV_DELIMITER,
    CSV_ENCODING,
    CSV_REPORT_NAME,
    JSON_REPORT_NAME,
    MARKDOWN_REPORT_NAME,
    ReportWriterSet,
)
from greenplan.placement.planting_plan import PlantingPlanComposer
from greenplan.species.species_selector import SpeciesSelectorFactory

from fixtures.explanation_checks import citations_violating_policy, unexplained_numbers
from fixtures.placement_factory import street_site


@pytest.fixture(scope="module")
def report(knowledge_root: Path) -> PlantingReport:
    site = street_site()
    plan = PlantingPlanComposer.from_knowledge(knowledge_root).compose(site)
    species = (
        SpeciesSelectorFactory.from_knowledge(knowledge_root).for_site(site).assign(plan.trees + plan.shrubs)
    )
    return ReportBuilder.from_knowledge(knowledge_root).build("Синтетическая улица", site, plan, species)


def test_summary_counts_match_explanations(report: PlantingReport) -> None:
    summary = report.summary
    assert summary.trees + summary.shrubs == len(report.plants)
    assert summary.rejected == len(report.rejections)
    assert summary.trees > 0 and summary.shrubs > 0
    assert sum(item.count for item in summary.species) == len(report.plants)


def test_applied_norms_and_rejection_reasons_are_counted(report: PlantingReport) -> None:
    rules = {row.rule_id: row for row in report.applied_norms}
    assert rules["sp42_gas_tree"].binding > 0
    assert rules["sp42_gas_tree"].description_ru == "Отступ от газопровода: 1,5 м"
    assert sum(row.count for row in report.rejection_reasons) == len(report.rejections)


def test_every_explanation_is_consistent_with_its_structure(report: PlantingReport) -> None:
    for explanation in (*report.plants, *report.rejections):
        assert explanation.explanation_ru
        assert unexplained_numbers(explanation) == set(), explanation.plant_id
    assert citations_violating_policy(report) == []


def test_writers_produce_json_csv_and_markdown(report: PlantingReport, tmp_path: Path) -> None:
    paths = ReportWriterSet.default().write_all(report, tmp_path / "reports")
    content = json.loads(paths[JSON_REPORT_NAME].read_text(encoding="utf-8"))
    with paths[CSV_REPORT_NAME].open(encoding=CSV_ENCODING, newline="") as stream:
        rows = list(csv.reader(stream, delimiter=CSV_DELIMITER))
    markdown = paths[MARKDOWN_REPORT_NAME].read_text(encoding="utf-8")
    assert [plant["plant_id"] for plant in content["plants"]] == [plant.plant_id for plant in report.plants]
    assert len(rows) == 1 + len(report.plants) + len(report.rejections)
    assert "## Применённые нормы" in markdown
    assert f"### {report.plants[0].plant_id}" in markdown
