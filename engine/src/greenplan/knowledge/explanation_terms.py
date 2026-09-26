from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from greenplan.knowledge.yaml_loader import load_yaml_mapping


@dataclass(frozen=True, slots=True)
class ObstacleTerms:
    name_ru: str
    from_ru: str
    zone_ru: str


@dataclass(frozen=True, slots=True)
class TargetTerms:
    name_ru: str
    genitive_ru: str


@dataclass(frozen=True, slots=True)
class ElementTerms:
    name_ru: str
    purpose_ru: str


@dataclass(frozen=True, slots=True)
class ReferencedText:
    text_ru: str
    source_refs: tuple[str, ...] = ()


class ExplanationTerms:
    def __init__(self, content: Mapping[str, Any]) -> None:
        self._content = content

    @classmethod
    def from_file(cls, path: Path) -> "ExplanationTerms":
        return cls(load_yaml_mapping(path))

    def target(self, target: str) -> TargetTerms:
        entry = self._section("targets").get(target, {})
        return TargetTerms(entry.get("name", target), entry.get("genitive", target))

    def obstacle(self, kind: str) -> ObstacleTerms:
        entry = self._section("obstacles").get(kind, {})
        from_ru = entry.get("from", f"от объекта «{kind}»")
        return ObstacleTerms(
            entry.get("name", kind), from_ru, entry.get("zone", f"зоне ограничений {from_ru}")
        )

    def status(self, status: str) -> str:
        return self._section("statuses").get(status, status)

    def severity(self, severity: str) -> str:
        return self._section("severities").get(severity, severity)

    def measurement(self, mode: str) -> str:
        return self._section("measurements").get(mode, mode)

    def norm_kind(self, rule_type: str) -> str:
        return self._section("norm_kinds").get(rule_type, rule_type)

    def site_violation(self, code: str) -> ReferencedText:
        return _referenced(self._section("site_violations").get(code), code)

    def site_warning(self, code: str) -> str:
        return self._section("site_warnings").get(code, code)

    def invasive(self, status: str) -> ReferencedText:
        return _referenced(self._section("invasive").get(status), status)

    def element(self, kind: str) -> ElementTerms:
        entry = (self._section("composition").get("elements") or {}).get(kind, {})
        return ElementTerms(entry.get("name", kind), " ".join(str(entry.get("purpose", "")).split()))

    def design_agents_note(self) -> str:
        return " ".join(str(self._section("design_agents").get("note", "")).split())

    def design_resolution(self, problem: str, measure: float, element_kind: str, planted: int) -> str:
        entry = (self._section("design_agents").get("problems") or {}).get(problem, {})
        name = entry.get("name", problem)
        unit = entry.get("unit", "")
        element = self.element(element_kind).name_ru
        return f"{name} ({format_measure(measure)} {unit}): {element} — {planted} шт."

    def density_exceeded(self, parts: dict[str, tuple[int, int]]) -> str:
        section = self._section("density")
        details = [
            str(section.get(target, "{count} / {limit}")).format(count=count, limit=limit)
            for target, (count, limit) in parts.items()
        ]
        return " ".join(str(section.get("exceeded", "{detail}")).split()).format(detail="; ".join(details))

    def tree_floor(self, expected: int, planned: int, limit: int) -> str:
        template = str(self._section("density").get("tree_floor", "{expected} → {planned}"))
        return " ".join(template.split()).format(expected=expected, planned=planned, limit=limit)

    def element_edge(self, edge_kind: str) -> str:
        return (self._section("composition").get("edges") or {}).get(edge_kind, "")

    def _section(self, name: str) -> Mapping[str, Any]:
        return self._content.get(name) or {}


def format_measure(value: float) -> str:
    return f"{value:,.0f}".replace(",", " ")


def _referenced(entry: Mapping[str, Any] | None, fallback: str) -> ReferencedText:
    if not entry:
        return ReferencedText(fallback)
    return ReferencedText(entry.get("text", fallback), tuple(entry.get("source_refs", ())))
