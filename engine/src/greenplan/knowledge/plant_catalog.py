import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from greenplan.domain.errors import KnowledgeValidationError
from greenplan.domain.norms import SHRUB, TREE
from greenplan.knowledge.yaml_loader import load_yaml_mapping, require_key

TARGET_BY_PLANT_TYPE = {"tree": TREE, "large_shrub": SHRUB, "shrub": SHRUB, "hedge": SHRUB}
STREET_SUITABLE = "yes"
NOT_STREET_SUITABLE = "no"
LIMITED_STREET_SUITABILITY = "limited"
UNKNOWN_STREET_SUITABILITY = "unknown"
INTEGER_PATTERN = re.compile(r"\d+")


@dataclass(frozen=True, slots=True)
class SpeciesTraits:
    gas_tolerance: str
    salt_tolerance: str
    moisture: str
    shade_tolerance: str
    dust_capture: str


@dataclass(frozen=True, slots=True)
class Species:
    key: str
    name_ru: str
    latin: str
    plant_type: str
    crown_diameter_m: float
    height_m: float
    crown_class: str | None = None
    coniferous: bool = False
    heating_min_axis_m: float | None = None
    street_suitability: str = UNKNOWN_STREET_SUITABILITY
    invasive_status: str | None = None
    block_candidates: tuple[str, ...] = ()
    reference_usage_total: int = 0
    traits: SpeciesTraits | None = None
    territory_table_name: str | None = None
    noise_barrier: bool = False

    @property
    def target(self) -> str | None:
        return TARGET_BY_PLANT_TYPE.get(self.plant_type)


@dataclass(frozen=True, slots=True)
class SelectionRule:
    context: str
    prefer: tuple[str, ...] = ()
    avoid: tuple[str, ...] = ()
    limited: tuple[str, ...] = ()
    max_crown_d_m: float | None = None
    max_height_m: float | None = None
    prefer_crown_class: str | None = None
    avoid_crown_class: str | None = None
    reason_ru: str = ""
    source_ref: str | None = None


class PlantCatalog:
    def __init__(self, species: Iterable[Species], rules: Iterable[SelectionRule] = ()) -> None:
        self._species = tuple(species)
        self._species_by_key = {item.key: item for item in self._species}
        self._rules = {rule.context: rule for rule in rules}

    @classmethod
    def from_file(cls, path: Path) -> "PlantCatalog":
        content = load_yaml_mapping(path)
        species = [_species_from(entry) for entry in require_key(content, "species", path)]
        rules = [_rule_from(entry) for entry in content.get("selection_rules", []) or []]
        return cls(species, rules)

    def species(self) -> tuple[Species, ...]:
        return self._species

    def species_for(self, target: str) -> tuple[Species, ...]:
        return tuple(item for item in self._species if item.target == target)

    def get(self, key: str) -> Species:
        if key not in self._species_by_key:
            raise KnowledgeValidationError(f"unknown species '{key}'")
        return self._species_by_key[key]

    def rule(self, context: str) -> SelectionRule | None:
        return self._rules.get(context)


def _species_from(entry: Mapping[str, Any]) -> Species:
    return Species(
        key=entry["key"],
        name_ru=entry["ru"],
        latin=entry.get("latin", ""),
        plant_type=entry["type"],
        crown_diameter_m=float(entry["crown_d_m"]),
        height_m=float(entry["height_m"]),
        crown_class=entry.get("crown_class"),
        coniferous=bool(entry.get("coniferous", False)),
        heating_min_axis_m=_optional_float(entry.get("heating_min_axis_m")),
        street_suitability=_street_suitability(entry.get("street_suitable")),
        invasive_status=entry.get("invasive_status"),
        block_candidates=tuple(entry.get("block_candidates", ())),
        reference_usage_total=_usage_total(entry.get("reference_usage") or {}),
        traits=_traits_from(entry.get("traits")),
        territory_table_name=entry.get("tsn_v6_name"),
        noise_barrier=bool(entry.get("noise_barrier", False)),
    )


def _traits_from(entry: Mapping[str, Any] | None) -> SpeciesTraits | None:
    if not entry:
        return None
    return SpeciesTraits(
        gas_tolerance=entry["gas"],
        salt_tolerance=entry["salt"],
        moisture=entry["moisture"],
        shade_tolerance=entry["shade"],
        dust_capture=entry["dust"],
    )


def _rule_from(entry: Mapping[str, Any]) -> SelectionRule:
    return SelectionRule(
        context=entry["context"],
        prefer=tuple(entry.get("prefer", ())),
        avoid=tuple(entry.get("avoid", ())),
        limited=tuple(entry.get("limited", ())),
        max_crown_d_m=_optional_float(entry.get("max_crown_d_m")),
        max_height_m=_optional_float(entry.get("max_height_m")),
        prefer_crown_class=entry.get("prefer_crown_class"),
        avoid_crown_class=entry.get("avoid_crown_class"),
        reason_ru=(entry.get("reason_ru") or "").strip(),
        source_ref=entry.get("source_ref"),
    )


def _street_suitability(value: Any) -> str:
    if value is True:
        return STREET_SUITABLE
    if value is False:
        return NOT_STREET_SUITABLE
    if value == LIMITED_STREET_SUITABILITY:
        return LIMITED_STREET_SUITABILITY
    return UNKNOWN_STREET_SUITABILITY


def _usage_total(usage: Mapping[str, Any]) -> int:
    return sum(int(token) for value in usage.values() for token in INTEGER_PATTERN.findall(str(value)))


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)
