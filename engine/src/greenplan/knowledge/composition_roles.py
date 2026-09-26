from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from greenplan.knowledge.yaml_loader import load_yaml_mapping

ROLES_FILE = Path("plants") / "composition_roles.yaml"


@dataclass(frozen=True, slots=True)
class SpeciesRole:
    species_keys: frozenset[str]
    reason_ru: str


class CompositionRoles:
    def __init__(self, roles: Mapping[str, SpeciesRole]) -> None:
        self._roles = dict(roles)

    @classmethod
    def from_knowledge(cls, knowledge_root: Path) -> "CompositionRoles":
        path = knowledge_root / ROLES_FILE
        if not path.is_file():
            return cls({})
        content: Mapping[str, Any] = load_yaml_mapping(path)
        return cls(
            {
                kind: SpeciesRole(frozenset(entry.get("species") or ()), str(entry.get("reason", "")))
                for kind, entry in (content.get("roles") or {}).items()
            }
        )

    def role(self, kind: str) -> SpeciesRole | None:
        return self._roles.get(kind)

    def suits(self, kind: str, species_key: str) -> bool:
        role = self._roles.get(kind)
        return role is not None and species_key in role.species_keys
