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
    VOLUME_COLUMNS,
    VOLUMES_REPORT_NAME,
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


def test_metrics_volumes_and_cost_are_reported(report: PlantingReport) -> None:
    metrics = report.metrics
    volumes = report.volumes
    assert metrics is not None and volumes is not None and report.cost is not None
    assert metrics.species_count >= 2
    assert 0 < metrics.max_species_share <= 1
    assert "деревья" in metrics.tiers and "кустарники" in metrics.tiers
    assert metrics.street_front_covered_m > 0
    assert volumes.trees == report.summary.trees
    assert volumes.shrubs == report.summary.shrubs
    assert sum(row.count for row in volumes.plants) == len(report.plants)
    assert report.cost.total_rub > 0
    assert report.cost.reference_range_rub == (10000000.0, 25000000.0)


def test_volumes_csv_lists_species_lawn_and_barriers(report: PlantingReport, tmp_path: Path) -> None:
    written = ReportWriterSet.default().write_all(report, tmp_path)
    assert VOLUMES_REPORT_NAME in written
    stream = (tmp_path / VOLUMES_REPORT_NAME).open(encoding=CSV_ENCODING)
    rows = list(csv.reader(stream, delimiter=CSV_DELIMITER))
    stream.close()
    assert rows[0] == list(VOLUME_COLUMNS)
    names = {row[0] for row in rows[1:]}
    assert "газон, м²" in names
    assert "корнезащита, м" in names


def test_markdown_shows_metrics_volumes_and_cost(report: PlantingReport, tmp_path: Path) -> None:
    ReportWriterSet.default().write_all(report, tmp_path)
    text = (tmp_path / MARKDOWN_REPORT_NAME).read_text(encoding="utf-8")
    assert "## Показатели плана" in text
    assert "## Ведомость объёмов" in text
    assert "## Ориентировочная стоимость" in text
    assert "Значения индикативные" in text
    assert "## Польза и композиция" in text
    assert "Элементы композиции: ряды" in text


def test_every_plant_explains_its_composition_element(report: PlantingReport) -> None:
    assert all(plant.element is not None for plant in report.plants)
    assert all("Элемент композиции:" in plant.explanation_ru for plant in report.plants)
    metrics = report.metrics
    assert metrics is not None
    assert 0.0 < metrics.open_lawn_share < 1.0
    assert metrics.street_front_share is not None and metrics.street_front_share > 0.0


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
