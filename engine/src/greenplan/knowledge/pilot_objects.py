from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from greenplan.knowledge.yaml_loader import load_yaml_mapping, require_key

PILOT_OBJECTS_FILE = Path("dataset") / "pilot_objects.yaml"


@dataclass(frozen=True, slots=True)
class PilotObject:
    object_id: str
    name: str
    level: str
    layer_scheme: str | None
    input_path: str
    reference_path: str | None

    @property
    def object_folder(self) -> str:
        return self.input_path.split("/")[0]


@dataclass(frozen=True, slots=True)
class PilotCatalog:
    dataset_root: str
    objects: tuple[PilotObject, ...]

    @classmethod
    def from_file(cls, path: Path) -> "PilotCatalog":
        content = load_yaml_mapping(path)
        meta = content.get("meta") or {}
        entries = require_key(content, "objects", path)
        return cls(
            dataset_root=str(meta.get("dataset_root", "")),
            objects=tuple(_object_from(entry) for entry in entries),
        )

    @classmethod
    def from_knowledge(cls, knowledge_root: Path) -> "PilotCatalog":
        return cls.from_file(knowledge_root / PILOT_OBJECTS_FILE)

    def of_levels(self, levels: Sequence[str] | None) -> tuple[PilotObject, ...]:
        if not levels:
            return self.objects
        wanted = {level.upper() for level in levels}
        return tuple(item for item in self.objects if item.level.upper() in wanted)

    def selected(
        self, levels: Sequence[str] | None, object_ids: Sequence[str] | None = None
    ) -> tuple[PilotObject, ...]:
        chosen = self.of_levels(levels)
        if not object_ids:
            return chosen
        wanted = set(object_ids)
        return tuple(item for item in chosen if item.object_id in wanted)


def _object_from(entry: dict[str, Any]) -> PilotObject:
    return PilotObject(
        object_id=entry["id"],
        name=entry.get("name", entry["id"]),
        level=entry.get("level", ""),
        layer_scheme=entry.get("layer_scheme"),
        input_path=entry["input"],
        reference_path=entry.get("reference"),
    )
