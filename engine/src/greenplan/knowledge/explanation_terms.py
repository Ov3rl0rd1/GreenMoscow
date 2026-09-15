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

    def invasive(self, status: str) -> ReferencedText:
        return _referenced(self._section("invasive").get(status), status)

    def _section(self, name: str) -> Mapping[str, Any]:
        return self._content.get(name) or {}


def _referenced(entry: Mapping[str, Any] | None, fallback: str) -> ReferencedText:
    if not entry:
        return ReferencedText(fallback)
    return ReferencedText(entry.get("text", fallback), tuple(entry.get("source_refs", ())))
