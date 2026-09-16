import csv
import json
from collections.abc import Iterable, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Protocol

from greenplan.explain.explanation_model import PlantExplanation
from greenplan.explain.number_format import format_number
from greenplan.explain.report_model import AppliedNormRow, PlantingReport

JSON_REPORT_NAME = "planting_report.json"
CSV_REPORT_NAME = "planting_report.csv"
MARKDOWN_REPORT_NAME = "planting_report.md"
CSV_DELIMITER = ";"
CSV_ENCODING = "utf-8-sig"
CSV_COLUMNS = (
    "plant_id",
    "status",
    "plant_type",
    "species",
    "x",
    "y",
    "crown_d_m",
    "rule_id",
    "actual_m",
    "required_m",
    "citation",
    "explanation_ru",
    "root_barrier_m",
)


class ReportWriter(Protocol):
    file_name: str

    def write(self, report: PlantingReport, directory: Path) -> Path: ...


class JsonReportWriter:
    file_name = JSON_REPORT_NAME

    def write(self, report: PlantingReport, directory: Path) -> Path:
        path = directory / self.file_name
        path.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2), encoding="utf-8")
        return path


class CsvReportWriter:
    file_name = CSV_REPORT_NAME

    def write(self, report: PlantingReport, directory: Path) -> Path:
        path = directory / self.file_name
        with path.open("w", encoding=CSV_ENCODING, newline="") as stream:
            writer = csv.writer(stream, delimiter=CSV_DELIMITER)
            writer.writerow(CSV_COLUMNS)
            writer.writerows(_csv_row(explanation) for explanation in (*report.plants, *report.rejections))
        return path


class MarkdownReportWriter:
    file_name = MARKDOWN_REPORT_NAME

    def write(self, report: PlantingReport, directory: Path) -> Path:
        path = directory / self.file_name
        path.write_text("\n".join(markdown_lines(report)) + "\n", encoding="utf-8")
        return path


class ReportWriterSet:
    def __init__(self, writers: Sequence[ReportWriter]) -> None:
        self._writers = tuple(writers)

    @classmethod
    def default(cls) -> "ReportWriterSet":
        return cls((JsonReportWriter(), CsvReportWriter(), MarkdownReportWriter()))

    def write_all(self, report: PlantingReport, directory: Path) -> dict[str, Path]:
        directory.mkdir(parents=True, exist_ok=True)
        return {writer.file_name: writer.write(report, directory) for writer in self._writers}


def markdown_lines(report: PlantingReport) -> list[str]:
    return [
        f"# {report.title}",
        "",
        *_summary_lines(report),
        *_species_lines(report),
        *_norm_lines(report),
        *_rejection_reason_lines(report),
        *_explanation_lines("Посадки", report.plants),
        *_explanation_lines("Отказы", report.rejections),
    ]


def _summary_lines(report: PlantingReport) -> list[str]:
    summary = report.summary
    share = format_number(summary.annotated_network_share * 100)
    return [
        "## Итог",
        "",
        f"- Деревьев: {summary.trees}, кустарников: {summary.shrubs} "
        f"(условно допустимых: {summary.conditional})",
        f"- Отклонено кандидатов (с объяснением причин): {summary.rejected}",
        f"- Корнезащита у условно допустимых деревьев: {format_number(summary.root_barrier_length_m)} м",
        f"- Лимиты плотности: деревьев не более {summary.max_trees}, "
        f"кустарников не более {summary.max_shrubs}; "
        f"шаг деревьев {format_number(summary.tree_spacing_m)} м, "
        f"кустарников {format_number(summary.shrub_spacing_m)} м",
        f"- Газон в границе работ: {format_number(summary.plantable_area_m2)} м²; "
        f"допустимо для дерева: {format_number(summary.tree_allowed_area_m2)} м²",
        f"- Граница участка: {summary.boundary_source}; газоны: {summary.lawn_source}",
        f"- Доля длины подземных сетей с распознанным диаметром: {share} %",
        f"- Неразрешённые внешние ссылки: {len(summary.unresolved_references)}",
        f"- Версия движка: {report.engine_version}",
        "",
        *_warning_lines(summary.warnings),
    ]


def _warning_lines(warnings: Sequence[str]) -> list[str]:
    if not warnings:
        return []
    return ["## Предупреждения", "", *(f"- {_capital(text)}" for text in warnings), ""]


def _capital(text: str) -> str:
    return text[:1].upper() + text[1:]


def _species_lines(report: PlantingReport) -> list[str]:
    rows = [
        f"| {_cell(item.name_ru)} | {item.plant_type} | {item.count} |" for item in report.summary.species
    ]
    return ["## Породы", "", "| Порода | Тип | Количество |", "|---|---|---:|", *rows, ""]


def _norm_lines(report: PlantingReport) -> list[str]:
    header = "| Норма | Строгость | Источник | Упоминаний | Определяющих | Сверка |"
    rows = [_norm_row(row) for row in report.applied_norms]
    return ["## Применённые нормы", "", header, "|---|---|---|---:|---:|---|", *rows, ""]


def _norm_row(row: AppliedNormRow) -> str:
    sources = _cell("; ".join(citation.text_ru for citation in row.citations))
    verification = _cell(", ".join(citation.verification for citation in row.citations))
    return (
        f"| {_cell(row.description_ru)} | {_cell(row.severity_ru)} | {sources} | "
        f"{row.mentions} | {row.binding} | {verification} |"
    )


def _rejection_reason_lines(report: PlantingReport) -> list[str]:
    rows = [f"| {_cell(row.description_ru)} | {row.count} |" for row in report.rejection_reasons]
    return ["## Основные причины отказов", "", "| Причина | Кандидатов |", "|---|---:|", *rows, ""]


def _explanation_lines(title: str, explanations: Iterable[PlantExplanation]) -> list[str]:
    lines = [f"## {title}", ""]
    for explanation in explanations:
        name = explanation.species.name_ru if explanation.species else explanation.plant_type
        lines.extend([f"### {explanation.plant_id} — {name}", "", explanation.explanation_ru, ""])
    return lines


def _csv_row(explanation: PlantExplanation) -> list[str]:
    primary = explanation.clearances[0] if explanation.clearances else None
    return [
        explanation.plant_id,
        explanation.status,
        explanation.plant_type,
        explanation.species.name_ru if explanation.species else "",
        str(explanation.x),
        str(explanation.y),
        str(explanation.crown_diameter_m),
        primary.rule_id if primary else explanation.primary_reason_code,
        str(primary.actual_m) if primary else "",
        str(primary.required_m) if primary else "",
        "; ".join(citation.text_ru for citation in primary.citations) if primary else "",
        explanation.explanation_ru,
        str(explanation.root_barrier_length_m),
    ]


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")
