from collections.abc import Iterable
from typing import Any

from greenplan.domain.norms import (
    DISTANCE_RULE,
    PLANT_TARGETS,
    ZONE_RULE,
    CompetingValue,
    NormRule,
)

ASSUMPTION_STATUS = "assumption"


def parse_norm_rule(entry: dict[str, Any]) -> NormRule:
    targets = _as_tuple(entry.get("target", PLANT_TARGETS))
    return NormRule(
        rule_id=entry["id"],
        rule_type=_rule_type(entry),
        obstacles=_as_tuple(entry.get("obstacle", ())),
        targets=targets,
        severity=entry.get("severity", "advisory"),
        distances=_distances(entry.get("distance_m"), targets),
        zone_m=_optional_float(entry.get("zone_m")),
        zone_by_voltage=_zones_by_voltage(entry.get("zone_by_voltage_kv", ())),
        measured_from=entry.get("measured_from", ""),
        source_refs=_source_refs(entry),
        competing=tuple(_competing(item) for item in entry.get("competing", []) or []),
        species_ru=_as_tuple(entry.get("species_ru", ())),
        condition_ru=entry.get("condition_ru", ""),
        rationale_ru=(entry.get("rationale_ru") or "").strip(),
        is_assumption=entry.get("status") == ASSUMPTION_STATUS,
    )


def referenced_citation_keys(entry: dict[str, Any]) -> set[str]:
    keys = set(_source_refs(entry))
    keys.update(item["source_ref"] for item in entry.get("competing", []) or [])
    if entry.get("assumption_ref"):
        keys.add(entry["assumption_ref"])
    return keys


def _rule_type(entry: dict[str, Any]) -> str:
    if "rule_type" in entry:
        return entry["rule_type"]
    if "zone_m" in entry or "zone_by_voltage_kv" in entry:
        return ZONE_RULE
    return DISTANCE_RULE


def _distances(raw: Any, targets: tuple[str, ...]) -> tuple[tuple[str, float | None], ...]:
    if isinstance(raw, dict):
        return tuple((target, _optional_float(raw.get(target))) for target in targets)
    return tuple((target, _optional_float(raw)) for target in targets)


def _zones_by_voltage(entries: Iterable[dict[str, Any]]) -> tuple[tuple[float, float], ...]:
    return tuple(sorted((float(item["max_kv"]), float(item["zone_m"])) for item in entries))


def _source_refs(entry: dict[str, Any]) -> tuple[str, ...]:
    if "source_refs" in entry:
        return tuple(entry["source_refs"])
    return (entry["source_ref"],) if "source_ref" in entry else ()


def _competing(item: dict[str, Any]) -> CompetingValue:
    return CompetingValue(item["source_ref"], _optional_float(item.get("distance_m")), item.get("row_ru"))


def _as_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    return tuple(value)


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)
