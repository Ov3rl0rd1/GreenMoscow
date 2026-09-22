import math
from collections.abc import Sequence
from dataclasses import dataclass

from greenplan.knowledge.invasive_registry import CONDITIONAL, EXCLUDED, InvasiveRegistry, InvasiveVerdict
from greenplan.knowledge.plant_catalog import NOT_STREET_SUITABLE, PlantCatalog, SelectionRule, Species
from greenplan.species.selection_texts import SelectionReason, SelectionTexts
from greenplan.species.site_context import NEAR_BUILDING, STREET_CARRIAGEWAY_ADJACENT, PlantingContext
from greenplan.species.species_settings import SpeciesSettings
from greenplan.species.territory_policy import LIMITED, UNLISTED, TerritoryAssessment, TerritoryPolicy

LEVEL_SCORE = {"high": 1.0, "medium": 0.0, "low": -1.0}
SHADE_SCORE = {"tolerant": 1.0, "medium": 0.0, "intolerant": -1.0}
HIGH_LEVEL = "high"
SHADE_TOLERANT = "tolerant"
TRAITS_SECTION = "traits"

__all__ = ["RankedSpecies", "SelectionReason", "SpeciesSuitability"]


@dataclass(frozen=True, slots=True)
class RankedSpecies:
    species: Species
    score: float
    invasive: InvasiveVerdict
    reasons: tuple[SelectionReason, ...]


class SpeciesSuitability:
    def __init__(
        self,
        catalog: PlantCatalog,
        registry: InvasiveRegistry,
        settings: SpeciesSettings,
        territory: TerritoryPolicy | None = None,
        texts: SelectionTexts | None = None,
    ) -> None:
        self._catalog = catalog
        self._settings = settings
        self._territory = territory
        self._texts = texts
        self._verdicts = {species.key: registry.verdict(species) for species in catalog.species()}

    @property
    def territory(self) -> TerritoryPolicy | None:
        return self._territory

    def ranked(self, target: str, context: PlantingContext) -> list[RankedSpecies]:
        rules = self._context_rules(context)
        ranked: list[RankedSpecies] = []
        for species in self._catalog.species_for(target):
            territory = self._territory.assess(species) if self._territory else None
            if not self._is_admissible(species, context, rules, territory):
                continue
            ranked.append(
                RankedSpecies(
                    species,
                    self._score(species, rules, context, territory),
                    self._verdicts[species.key],
                    self._reasons(species, rules, context, territory),
                )
            )
        return sorted(ranked, key=lambda item: -item.score)

    def excluded(self, target: str) -> list[tuple[Species, str]]:
        if self._territory is None:
            return []
        return [
            (species, text)
            for species in self._catalog.species_for(target)
            if (text := self._territory.exclusion_text(species)) is not None
        ]

    def _context_rules(self, context: PlantingContext) -> list[SelectionRule]:
        return [rule for tag in sorted(context.tags) if (rule := self._catalog.rule(tag)) is not None]

    def _is_admissible(
        self,
        species: Species,
        context: PlantingContext,
        rules: Sequence[SelectionRule],
        territory: TerritoryAssessment | None,
    ) -> bool:
        return (
            self._passes_invasive_policy(self._verdicts[species.key])
            and (territory is None or territory.admissible)
            and not (self._territory is not None and self._territory.excludes_conifer(species, context))
            and _keeps_heating_distance(species, context)
            and _suits_street(species, context)
            and all(_passes_rule(species, rule) for rule in rules)
        )

    def _passes_invasive_policy(self, verdict: InvasiveVerdict) -> bool:
        if verdict.status == EXCLUDED:
            return False
        return verdict.status != CONDITIONAL or self._settings.allow_conditional_species

    def _score(
        self,
        species: Species,
        rules: Sequence[SelectionRule],
        context: PlantingContext,
        territory: TerritoryAssessment | None,
    ) -> float:
        settings = self._settings
        score = settings.reference_usage_weight * math.log1p(species.reference_usage_total)
        for rule in rules:
            score += settings.prefer_bonus if species.key in rule.prefer else 0.0
            score -= settings.limited_penalty if species.key in rule.limited else 0.0
            if rule.prefer_crown_class is not None and species.crown_class == rule.prefer_crown_class:
                score += settings.crown_class_bonus
        return score + self._territory_score(territory) + self._trait_score(species, context)

    def _territory_score(self, territory: TerritoryAssessment | None) -> float:
        if territory is None:
            return 0.0
        if territory.kind == LIMITED:
            return -self._settings.territory_limited_penalty
        if territory.kind == UNLISTED:
            return -self._settings.unlisted_penalty
        return 0.0

    def _trait_score(self, species: Species, context: PlantingContext) -> float:
        settings = self._settings
        traits = species.traits
        score = 0.0
        if traits is not None and STREET_CARRIAGEWAY_ADJACENT in context.tags:
            score += settings.trait_bonus * (
                LEVEL_SCORE[traits.gas_tolerance] + LEVEL_SCORE[traits.salt_tolerance]
            )
        if traits is not None and NEAR_BUILDING in context.tags:
            score += settings.trait_bonus * SHADE_SCORE[traits.shade_tolerance]
        if self._protects_from_noise(species, context):
            score += settings.noise_bonus
        return score

    def _protects_from_noise(self, species: Species, context: PlantingContext) -> bool:
        return (
            species.noise_barrier
            and self._territory is not None
            and self._territory.category.noise_protection
            and STREET_CARRIAGEWAY_ADJACENT in context.tags
        )

    def _reasons(
        self,
        species: Species,
        rules: Sequence[SelectionRule],
        context: PlantingContext,
        territory: TerritoryAssessment | None,
    ) -> tuple[SelectionReason, ...]:
        reasons: list[SelectionReason] = []
        if territory is not None and territory.reason is not None:
            reasons.append(territory.reason)
        reasons.extend(self._trait_reasons(species, context))
        reasons.extend(
            SelectionReason(f"context:{rule.context}", rule.reason_ru, rule.source_ref)
            for rule in rules
            if rule.reason_ru and (species.key in rule.prefer or not rule.prefer)
        )
        if self._texts is not None and species.reference_usage_total > 0:
            reasons.append(
                self._texts.reason("practice", "reference_usage", count=species.reference_usage_total)
            )
        return tuple(reasons)

    def _trait_reasons(self, species: Species, context: PlantingContext) -> list[SelectionReason]:
        if self._texts is None or species.traits is None:
            return []
        traits = species.traits
        near_road = STREET_CARRIAGEWAY_ADJACENT in context.tags
        codes = [
            code
            for code, applies in (
                ("gas_high_near_road", near_road and traits.gas_tolerance == HIGH_LEVEL),
                ("salt_high_near_road", near_road and traits.salt_tolerance == HIGH_LEVEL),
                ("dust_high_near_road", near_road and traits.dust_capture == HIGH_LEVEL),
                (
                    "shade_tolerant_near_building",
                    NEAR_BUILDING in context.tags and traits.shade_tolerance == SHADE_TOLERANT,
                ),
                ("noise_barrier", self._protects_from_noise(species, context)),
            )
            if applies
        ]
        return [self._texts.reason(TRAITS_SECTION, code) for code in codes]


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
