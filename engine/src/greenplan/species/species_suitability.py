import math
from collections.abc import Sequence
from dataclasses import dataclass

from greenplan.knowledge.invasive_registry import CONDITIONAL, EXCLUDED, InvasiveRegistry, InvasiveVerdict
from greenplan.knowledge.plant_catalog import NOT_STREET_SUITABLE, PlantCatalog, SelectionRule, Species
from greenplan.species.site_context import STREET_CARRIAGEWAY_ADJACENT, PlantingContext
from greenplan.species.species_settings import SpeciesSettings


@dataclass(frozen=True, slots=True)
class SelectionReason:
    code: str
    reason_ru: str
    source_ref: str | None = None


@dataclass(frozen=True, slots=True)
class RankedSpecies:
    species: Species
    score: float
    invasive: InvasiveVerdict
    reasons: tuple[SelectionReason, ...]


class SpeciesSuitability:
    def __init__(self, catalog: PlantCatalog, registry: InvasiveRegistry, settings: SpeciesSettings) -> None:
        self._catalog = catalog
        self._settings = settings
        self._verdicts = {species.key: registry.verdict(species) for species in catalog.species()}

    def ranked(self, target: str, context: PlantingContext) -> list[RankedSpecies]:
        rules = self._context_rules(context)
        ranked = [
            RankedSpecies(species, self._score(species, rules), self._verdicts[species.key], _reasons(rules))
            for species in self._catalog.species_for(target)
            if self._is_admissible(species, context, rules)
        ]
        return sorted(ranked, key=lambda item: -item.score)

    def _context_rules(self, context: PlantingContext) -> list[SelectionRule]:
        return [rule for tag in sorted(context.tags) if (rule := self._catalog.rule(tag)) is not None]

    def _is_admissible(
        self, species: Species, context: PlantingContext, rules: Sequence[SelectionRule]
    ) -> bool:
        return (
            self._passes_invasive_policy(self._verdicts[species.key])
            and _keeps_heating_distance(species, context)
            and _suits_street(species, context)
            and all(_passes_rule(species, rule) for rule in rules)
        )

    def _passes_invasive_policy(self, verdict: InvasiveVerdict) -> bool:
        if verdict.status == EXCLUDED:
            return False
        return verdict.status != CONDITIONAL or self._settings.allow_conditional_species

    def _score(self, species: Species, rules: Sequence[SelectionRule]) -> float:
        settings = self._settings
        score = settings.reference_usage_weight * math.log1p(species.reference_usage_total)
        for rule in rules:
            score += settings.prefer_bonus if species.key in rule.prefer else 0.0
            score -= settings.limited_penalty if species.key in rule.limited else 0.0
            if rule.prefer_crown_class is not None and species.crown_class == rule.prefer_crown_class:
                score += settings.crown_class_bonus
        return score


def _keeps_heating_distance(species: Species, context: PlantingContext) -> bool:
    return species.heating_min_axis_m is None or context.heating_axis_distance_m >= species.heating_min_axis_m


def _suits_street(species: Species, context: PlantingContext) -> bool:
    return (
        STREET_CARRIAGEWAY_ADJACENT not in context.tags or species.street_suitability != NOT_STREET_SUITABLE
    )


def _passes_rule(species: Species, rule: SelectionRule) -> bool:
    if species.key in rule.avoid:
        return False
    if rule.max_crown_d_m is not None and species.crown_diameter_m > rule.max_crown_d_m:
        return False
    if rule.max_height_m is not None and species.height_m > rule.max_height_m:
        return False
    return rule.avoid_crown_class is None or species.crown_class != rule.avoid_crown_class


def _reasons(rules: Sequence[SelectionRule]) -> tuple[SelectionReason, ...]:
    return tuple(
        SelectionReason(f"context:{rule.context}", rule.reason_ru, rule.source_ref) for rule in rules
    )
