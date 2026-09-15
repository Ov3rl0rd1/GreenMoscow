import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from greenplan.explain.number_format import format_number
from greenplan.verify.verification_model import VerificationReport

JSON_VERIFICATION_NAME = "verification_report.json"
MARKDOWN_VERIFICATION_NAME = "verification_report.md"


def write_verification_json(report: VerificationReport, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    content = {
        **asdict(report),
        "is_valid": report.is_valid,
        "integrity_is_intact": report.integrity.is_intact,
    }
    path = directory / JSON_VERIFICATION_NAME
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_verification_markdown(report: VerificationReport, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / MARKDOWN_VERIFICATION_NAME
    path.write_text("\n".join(verification_markdown_lines(report)) + "\n", encoding="utf-8")
    return path


def verification_markdown_lines(report: VerificationReport) -> list[str]:
    integrity = report.integrity
    verdict = "пройдена" if report.is_valid else "НЕ пройдена"
    counts = Counter(violation.code for violation in report.violations)
    lines = [
        "# Независимая проверка плана посадок",
        "",
        f"- Файл: `{report.output_path}`",
        f"- Проверка: **{verdict}**",
        f"- Посадок проверено: {report.plants_checked}",
        f"- Нарушений: {len(report.violations)}",
        f"- Исходные сущности: пропало {len(integrity.missing_handles)}, "
        f"изменено {len(integrity.changed_handles)}",
        f"- Изменённые исходные слои: {len(integrity.changed_layers)}; "
        f"пропавшие блоки: {len(integrity.missing_blocks)}",
        "",
        "## Нарушения по видам",
        "",
        "| Код | Количество |",
        "|---|---:|",
        *(f"| {code} | {count} |" for code, count in counts.most_common()),
        "",
        "## Нарушения",
        "",
        "| Посадка | Код | Факт, м | Требуется, м | Препятствие |",
        "|---|---|---:|---:|---|",
    ]
    lines.extend(
        f"| {item.plant_id} | {item.code} | {_optional_number(item.actual_m)} | "
        f"{_optional_number(item.required_m)} | {item.obstacle_kind} |"
        for item in report.violations
    )
    return lines


def _optional_number(value: float | None) -> str:
    return "" if value is None else format_number(value)
