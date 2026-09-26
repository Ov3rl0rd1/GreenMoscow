import csv
import json
from collections.abc import Iterable, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Protocol

from greenplan.explain.explanation_model import PlantExplanation
from greenplan.explain.number_format import format_number
from greenplan.explain.plan_metrics import CostEstimate, PlanMetrics, VolumeStatement
from greenplan.explain.report_model import AppliedNormRow, PlantingReport, ReportSummary
from greenplan.placement.score_maps import MODEL_GUIDANCE

ELEMENT_NAMES_RU = {
    "row": "ряды",
    "group": "группы деревьев",
    "solitary": "солитёры",
    "hedge": "живые изгороди",
    "shrub_group": "куртины",
}

JSON_REPORT_NAME = "planting_report.json"
CSV_REPORT_NAME = "planting_report.csv"
MARKDOWN_REPORT_NAME = "planting_report.md"
VOLUMES_REPORT_NAME = "volumes.csv"
VOLUME_COLUMNS = ("name_ru", "plant_type", "count")
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


class VolumesReportWriter:
    file_name = VOLUMES_REPORT_NAME

    def write(self, report: PlantingReport, directory: Path) -> Path:
        path = directory / self.file_name
        volumes = report.volumes
        with path.open("w", encoding=CSV_ENCODING, newline="") as stream:
            writer = csv.writer(stream, delimiter=CSV_DELIMITER)
            writer.writerow(VOLUME_COLUMNS)
            if volumes is not None:
                writer.writerows([row.name_ru, row.plant_type, row.count] for row in volumes.plants)
                writer.writerow(["газон, м²", "lawn", volumes.lawn_area_m2])
                writer.writerow(["корнезащита, м", "root_barrier", volumes.root_barrier_length_m])
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
        return cls((JsonReportWriter(), CsvReportWriter(), VolumesReportWriter(), MarkdownReportWriter()))

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


def guidance_line(summary: ReportSummary) -> str:
    if summary.guidance_source != MODEL_GUIDANCE:
        return (
            "Размещение: правила движка — места выбраны по отступам и краям газона, "
            "количество ограничено нормативом плотности"
        )
    return (
        "Размещение: модель, обученная на проектных решениях датасета, предложила места и количество "
        f"(деревьев около {summary.expected_trees}, кустарников около {summary.expected_shrubs}); "
        "каждая точка проверена нормами, норматив плотности — верхний предел"
    )


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
        *([f"- {_capital(summary.territory_ru)}"] if summary.territory_ru else []),
        f"- {guidance_line(summary)}",
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
        *_journal_lines(summary.journal),
        *_metric_lines(report.metrics),
        *_volume_lines(report.volumes),
        *_cost_lines(report.cost),
        *_excluded_lines(summary.excluded_species),
    ]


def _journal_lines(journal: Sequence[str]) -> list[str]:
    if not journal:
        return []
    return ["## Доработка плана агентами", "", *(f"- {_capital(text)}" for text in journal), ""]


def _warning_lines(warnings: Sequence[str]) -> list[str]:
    if not warnings:
        return []
    return ["## Предупреждения", "", *(f"- {_capital(text)}" for text in warnings), ""]


def _metric_lines(metrics: PlanMetrics | None) -> list[str]:
    if metrics is None:
        return []
    share = format_number(metrics.max_species_share * 100)
    listed = format_number(metrics.listed_species_share * 100)
    crown = format_number(metrics.crown_share_of_plantable * 100)
    return [
        "## Показатели плана",
        "",
        f"- Видов в плане: {metrics.species_count}; максимальная доля одного вида: {share} %",
        f"- Ярусы: {', '.join(metrics.tiers) if metrics.tiers else 'не сформированы'}",
        f"- Проекция крон: {format_number(metrics.crown_projection_m2)} м² ({crown} % газона)",
        f"- Фронт вдоль проезжей части под кронами: {format_number(metrics.street_front_covered_m)} м",
        f"- Доля пород из ассортимента ДПиООС: {listed} %",
        "",
        *_benefit_lines(metrics),
    ]


def share_text(share: float | None) -> str:
    return "края на чертеже не распознаны" if share is None else f"{format_number(share * 100)} %"


def _benefit_lines(metrics: PlanMetrics) -> list[str]:
    elements = ", ".join(f"{ELEMENT_NAMES_RU.get(kind, kind)} — {count}" for kind, count in metrics.elements)
    return [
        "## Польза и композиция",
        "",
        f"- Фронт проезжей части, отделённый посадками: {share_text(metrics.street_front_share)}",
        f"- Тротуары под кронами деревьев: {share_text(metrics.sidewalk_shade_share)}",
        f"- Газон, оставленный открытым: {format_number(metrics.open_lawn_share * 100)} %",
        f"- Элементы композиции: {elements if elements else 'не сформированы'}",
        "",
    ]


def _volume_lines(volumes: VolumeStatement | None) -> list[str]:
    if volumes is None:
        return []
    rows = [f"| {_cell(row.name_ru)} | {row.plant_type} | {row.count} |" for row in volumes.plants]
    return [
        "## Ведомость объёмов",
        "",
        "| Порода | Тип | Количество, шт. |",
        "|---|---|---|",
        *rows,
        "",
        f"- Газон в границе работ: {format_number(volumes.lawn_area_m2)} м²",
        f"- Корнезащита: {format_number(volumes.root_barrier_length_m)} м",
        "",
    ]


def _cost_lines(cost: CostEstimate | None) -> list[str]:
    if cost is None:
        return []
    lines = [
        "## Ориентировочная стоимость",
        "",
        f"- Итого: {format_number(cost.total_rub)} ₽ "
        f"({format_number(cost.per_hectare_rub)} ₽ на гектар озеленяемой площади)",
    ]
    if cost.reference_range_rub is not None:
        low, high = cost.reference_range_rub
        verdict = "в ориентире" if cost.within_reference_range else "вне ориентира"
        lines.append(
            f"- Ориентир постановщика: {format_number(low)}–{format_number(high)} ₽ на гектар — {verdict}"
        )
    lines.extend(["- Значения индикативные: прайсы питомников и нормативы обновляются регулярно", ""])
    return lines


def _excluded_lines(excluded: Sequence[str]) -> list[str]:
    if not excluded:
        return []
    heading = "## Породы ассортимента, не применённые в этой категории территории"
    return [heading, "", *(f"- {text}" for text in excluded), ""]


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
