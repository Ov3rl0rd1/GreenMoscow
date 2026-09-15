from pathlib import Path

from greenplan.domain.errors import KnowledgeValidationError
from greenplan.domain.norms import NormRule, NormsDefaults
from greenplan.knowledge.citations_repository import CitationsRepository
from greenplan.knowledge.norm_rule_parser import parse_norm_rule, referenced_citation_keys
from greenplan.knowledge.yaml_loader import load_yaml_mapping, require_key


class NormsRepository:
    def __init__(
        self, rules: tuple[NormRule, ...], defaults: NormsDefaults, citations: CitationsRepository
    ) -> None:
        self._rules = rules
        self.defaults = defaults
        self.citations = citations

    @classmethod
    def from_knowledge(cls, knowledge_root: Path) -> "NormsRepository":
        citations = CitationsRepository.from_file(knowledge_root / "rules" / "citations.yaml")
        return cls.from_files(knowledge_root / "rules" / "norms.yaml", citations)

    @classmethod
    def from_files(cls, norms_path: Path, citations: CitationsRepository) -> "NormsRepository":
        content = load_yaml_mapping(norms_path)
        meta = require_key(content, "meta", norms_path)
        entries = require_key(content, "rules", norms_path)
        _validate_references(entries, meta, citations, norms_path)
        rules = tuple(parse_norm_rule(entry) for entry in entries)
        _validate_unique_ids(rules, norms_path)
        return cls(rules, _defaults_from(meta), citations)

    def rules(self) -> tuple[NormRule, ...]:
        return self._rules

    def rule(self, rule_id: str) -> NormRule:
        found = next((rule for rule in self._rules if rule.rule_id == rule_id), None)
        if found is None:
            raise KnowledgeValidationError(f"unknown norm rule '{rule_id}'")
        return found


def _validate_references(entries: list, meta: dict, citations: CitationsRepository, source: Path) -> None:
    keys = {key for entry in entries for key in referenced_citation_keys(entry)}
    keys.add(meta["crown_rule"]["source_ref"])
    missing = sorted(key for key in keys if not citations.contains(key))
    if missing:
        raise KnowledgeValidationError(f"unresolved citation keys in {source}: {missing}")


def _validate_unique_ids(rules: tuple[NormRule, ...], source: Path) -> None:
    identifiers = [rule.rule_id for rule in rules]
    duplicates = sorted({identifier for identifier in identifiers if identifiers.count(identifier) > 1})
    if duplicates:
        raise KnowledgeValidationError(f"duplicate rule ids in {source}: {duplicates}")


def _defaults_from(meta: dict) -> NormsDefaults:
    defaults = meta["defaults"]
    return NormsDefaults(
        crown_base_diameter_m=float(meta["crown_rule"]["base_crown_diameter_m"]),
        unknown_pipe_outer_diameter_m=float(defaults["unknown_pipe_outer_diameter_m"]),
        unknown_heating_channel_width_m=float(defaults["unknown_heating_channel_width_m"]),
        trunk_diameter_at_planting_m=float(defaults["trunk_diameter_at_planting_m"]),
        crown_rule_source_ref=meta["crown_rule"]["source_ref"],
    )
