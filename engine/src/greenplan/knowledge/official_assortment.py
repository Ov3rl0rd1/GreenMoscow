from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from greenplan.domain.errors import KnowledgeValidationError
from greenplan.knowledge.yaml_loader import load_yaml_mapping, require_key

OFFICIAL_ASSORTMENT_FILE = Path("plants") / "official_assortment.yaml"
MAIN = "main"
ADDITIONAL = "additional"
PERSPECTIVE = "perspective"
LEVEL_ORDER = (MAIN, ADDITIONAL, PERSPECTIVE)
ALLOWED_MARK = "+"
SPREAD_CONTROL_NOTE = 1
CHILDREN_NOTE = 2
ROAD_SENSITIVE_NOTE = 5
TREE_GROUPS = ("conifer_tree", "deciduous_tree")


@dataclass(frozen=True, slots=True)
class OfficialEntry:
    name_ru: str
    level: str
    group: str
    notes: tuple[int, ...]
    columns: Mapping[str, str | None]

    def allows(self, columns: Sequence[str]) -> bool:
        return bool(columns) and all(self.columns.get(column) == ALLOWED_MARK for column in columns)

    def has_note(self, number: int) -> bool:
        return number in self.notes

    @property
    def level_rank(self) -> int:
        return LEVEL_ORDER.index(self.level)

    @property
    def is_tree(self) -> bool:
        return self.group in TREE_GROUPS


class OfficialAssortment:
    def __init__(
        self,
        entries: Sequence[OfficialEntry],
        column_names: Mapping[str, str],
        notes: Mapping[int, str],
    ) -> None:
        self._entries: dict[str, list[OfficialEntry]] = defaultdict(list)
        for entry in entries:
            self._entries[normalized(entry.name_ru)].append(entry)
        self._column_names = dict(column_names)
        self._notes = dict(notes)

    @classmethod
    def from_knowledge(cls, knowledge_root: Path) -> "OfficialAssortment":
        path = knowledge_root / OFFICIAL_ASSORTMENT_FILE
        content = load_yaml_mapping(path)
        return cls(
            entries=[_entry_from(item) for item in require_key(content, "species", path)],
            column_names={
                column["id"]: column["short_ru"] for column in require_key(content, "columns", path)
            },
            notes={int(number): text for number, text in require_key(content, "notes", path).items()},
        )

    def entries(self, names: Sequence[str], is_tree: bool) -> tuple[OfficialEntry, ...]:
        missing = [name for name in names if normalized(name) not in self._entries]
        if missing:
            raise KnowledgeValidationError(f"names are not in the official assortment: {missing}")
        return tuple(entry for name in names for entry in self._matching_form(name, is_tree))

    def _matching_form(self, name: str, is_tree: bool) -> list[OfficialEntry]:
        candidates = self._entries[normalized(name)]
        same_form = [entry for entry in candidates if entry.is_tree == is_tree]
        return same_form or candidates

    def column_ru(self, column: str) -> str:
        return self._column_names[column]

    def column_ids(self) -> tuple[str, ...]:
        return tuple(self._column_names)

    def note_ru(self, number: int) -> str:
        return self._notes[number]

    def __len__(self) -> int:
        return sum(len(entries) for entries in self._entries.values())


def normalized(name: str) -> str:
    return " ".join(name.lower().replace("ё", "е").split())


def _entry_from(item: Mapping[str, Any]) -> OfficialEntry:
    return OfficialEntry(
        name_ru=item["name_ru"],
        level=item["level"],
        group=item["group"],
        notes=tuple(item.get("notes") or ()),
        columns=dict(item["columns"]),
    )
