from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from greenplan.knowledge.yaml_loader import load_yaml_mapping

REASONS_FILE = Path("plants") / "selection_reasons.yaml"
ALTERNATIVES_SECTION = "alternatives"


@dataclass(frozen=True, slots=True)
class SelectionReason:
    code: str
    reason_ru: str
    source_ref: str | None = None


class SelectionTexts:
    def __init__(self, content: Mapping[str, Any]) -> None:
        self._content = content

    @classmethod
    def from_knowledge(cls, knowledge_root: Path) -> "SelectionTexts":
        return cls(load_yaml_mapping(knowledge_root / REASONS_FILE))

    def reason(self, section: str, code: str, **values: object) -> SelectionReason:
        entry = self._content[section][code]
        return SelectionReason(f"{section}:{code}", entry["text"].format(**values), entry.get("source_ref"))

    def alternative(self, code: str, **values: object) -> str:
        return self._content[ALTERNATIVES_SECTION][code].format(**values)

    def source_refs(self) -> set[str]:
        return {
            entry["source_ref"]
            for section in self._content.values()
            if isinstance(section, Mapping)
            for entry in section.values()
            if isinstance(entry, Mapping) and entry.get("source_ref")
        }
