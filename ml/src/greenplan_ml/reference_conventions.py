import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from greenplan.knowledge.yaml_loader import load_yaml_mapping, require_key

TREE_TYPE = "tree"
SHRUB_TYPE = "shrub"
HEDGE_TYPE = "hedge"
MIXED_TYPE = "mixed"
SHRUB_OR_TREE_TYPE = "shrub_or_tree"
PROPOSED_STATUS = "proposed"
SPECIES_GROUP = "species"
PLANTED_TYPES = frozenset({TREE_TYPE, SHRUB_TYPE, HEDGE_TYPE, MIXED_TYPE, SHRUB_OR_TREE_TYPE})


@dataclass(frozen=True, slots=True)
class LayerRule:
    pattern: re.Pattern[str]
    plant_type: str
    status: str


@dataclass(frozen=True, slots=True)
class LayerMatch:
    scheme_id: str
    plant_type: str
    status: str
    species_ru: str


@dataclass(frozen=True, slots=True)
class ReferenceScheme:
    scheme_id: str
    rules: tuple[LayerRule, ...]
    normalizers: tuple[tuple[re.Pattern[str], str], ...]

    def match(self, layer: str) -> LayerMatch | None:
        normalized = self.normalize(layer)
        for rule in self.rules:
            found = rule.pattern.search(normalized)
            if found is not None:
                return LayerMatch(self.scheme_id, rule.plant_type, rule.status, _species_of(found))
        return None

    def normalize(self, layer: str) -> str:
        normalized = layer
        for pattern, replacement in self.normalizers:
            normalized = pattern.sub(replacement, normalized)
        return normalized


class ReferenceLayerConventions:
    def __init__(self, schemes: Sequence[ReferenceScheme]) -> None:
        self._schemes = tuple(schemes)
        self._by_id = {scheme.scheme_id: scheme for scheme in self._schemes}

    @classmethod
    def from_file(cls, path: Path) -> "ReferenceLayerConventions":
        entries = require_key(load_yaml_mapping(path), "schemes", path)
        return cls([_scheme_from(entry) for entry in entries])

    def schemes(self) -> tuple[ReferenceScheme, ...]:
        return self._schemes

    def scheme(self, scheme_id: str) -> ReferenceScheme | None:
        return self._by_id.get(scheme_id)

    def best_scheme(self, layers: Iterable[str]) -> ReferenceScheme | None:
        names = list(layers)
        scored = [
            (sum(1 for layer in names if scheme.match(layer) is not None), scheme)
            for scheme in self._schemes
        ]
        matches, scheme = max(scored, key=lambda item: item[0], default=(0, None))
        return scheme if matches > 0 else None


def _scheme_from(entry: Mapping[str, Any]) -> ReferenceScheme:
    rules = tuple(
        LayerRule(re.compile(rule["regex"]), rule["type"], rule.get("status", PROPOSED_STATUS))
        for rule in entry.get("rules", ())
    )
    normalizers = tuple(
        (re.compile(item["pattern"]), item.get("replace", "")) for item in entry.get("normalizers", ())
    )
    return ReferenceScheme(entry["id"], rules, normalizers)


def _species_of(found: re.Match[str]) -> str:
    if SPECIES_GROUP not in found.groupdict():
        return ""
    return (found.group(SPECIES_GROUP) or "").strip()
