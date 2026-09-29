from dataclasses import asdict
from typing import Any

from greenplan.domain.norms import NormRule
from greenplan.explain.citation_policy import CitationPolicy
from greenplan.knowledge.norms_repository import NormsRepository


def norms_payload(repository: NormsRepository) -> dict[str, Any]:
    policy = CitationPolicy(repository.citations)
    return {
        "defaults": asdict(repository.defaults),
        "rules": [rule_payload(rule, policy) for rule in repository.rules()],
    }


def rule_payload(rule: NormRule, policy: CitationPolicy) -> dict[str, Any]:
    return {
        "id": rule.rule_id,
        "type": rule.rule_type,
        "severity": rule.severity,
        "obstacles": list(rule.obstacles),
        "targets": list(rule.targets),
        "distances_m": dict(rule.distances),
        "zone_m": rule.zone_m,
        "zone_by_voltage_kv": [{"max_kv": max_kv, "zone_m": zone} for max_kv, zone in rule.zone_by_voltage],
        "measured_from": rule.measured_from,
        "measured_to": rule.measured_to,
        "species_ru": list(rule.species_ru),
        "condition_ru": rule.condition_ru,
        "is_assumption": rule.is_assumption,
        "sources": [asdict(policy.view(key)) for key in rule.source_refs],
    }
