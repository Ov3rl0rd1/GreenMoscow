from dataclasses import dataclass

from greenplan.domain.norms import TREE
from greenplan.knowledge.invasive_registry import ALLOWED_WITH_CONTROL, InvasiveVerdict
from greenplan.knowledge.official_assortment import (
    CHILDREN_NOTE,
    ROAD_SENSITIVE_NOTE,
    SPREAD_CONTROL_NOTE,
    OfficialAssortment,
    OfficialEntry,
)
from greenplan.knowledge.plant_catalog import Species
from greenplan.knowledge.territory_catalog import TerritoryCatalog, TerritoryCategory
from greenplan.species.selection_texts import SelectionReason, SelectionTexts
from greenplan.species.site_context import STREET_CARRIAGEWAY_ADJACENT, PlantingContext

RECOMMENDED = "recommended"
LIMITED = "limited"
UNLISTED = "unlisted"
FORBIDDEN = "forbidden"
TERRITORY_SECTION = "territory"
OFFICIAL_KIND_PREFIX = "official_"
SPREAD_CONTROL_SOURCE_REF = "dpioos_assortment_notes"
SPREAD_CONTROL_GROUP = "ДПиООС:[1]"
EXPLAINED_NOTES = (3, 4, 6, 7)


@dataclass(frozen=True, slots=True)
class TerritoryAssessment:
    kind: str
    reason: SelectionReason | None
    entry: OfficialEntry | None = None

    @property
    def admissible(self) -> bool:
        return self.kind != FORBIDDEN


class TerritoryPolicy:
    def __init__(
        self,
        catalog: TerritoryCatalog,
        category: TerritoryCategory,
        texts: SelectionTexts,
        official: OfficialAssortment,
    ) -> None:
        self._catalog = catalog
        self._category = category
        self._texts = texts
        self._official = official
        self._column_ru = catalog.column_ru(category.tsn_column)
        self._official_columns_ru = "; ".join(
            official.column_ru(column) for column in category.official_columns
        )

    @property
    def category(self) -> TerritoryCategory:
        return self._category

    def assess(self, species: Species) -> TerritoryAssessment:
        entries = self.official_entries(species)
        return self._official_assessment(entries) if entries else self._fallback_assessment(species)

    def official_entries(self, species: Species) -> tuple[OfficialEntry, ...]:
        return self._official.entries(species.official_names, species.target == TREE)

    def invasive_override(self, species: Species) -> InvasiveVerdict | None:
        if not any(entry.has_note(SPREAD_CONTROL_NOTE) for entry in self.official_entries(species)):
            return None
        return InvasiveVerdict(ALLOWED_WITH_CONTROL, (SPREAD_CONTROL_SOURCE_REF,), (SPREAD_CONTROL_GROUP,))

    def excludes_near_carriageway(
        self, species: Species, assessment: TerritoryAssessment | None, context: PlantingContext
    ) -> bool:
        if STREET_CARRIAGEWAY_ADJACENT not in context.tags:
            return False
        if assessment is not None and assessment.entry is not None:
            return assessment.entry.has_note(ROAD_SENSITIVE_NOTE)
        return species.coniferous and not self._category.conifers_near_carriageway

    def exclusion_text(self, species: Species) -> str | None:
        assessment = self.assess(species)
        if not assessment.admissible:
            return self._forbidden_text(species)
        if self._category.conifers_near_carriageway:
            return None
        if assessment.entry is not None and assessment.entry.has_note(ROAD_SENSITIVE_NOTE):
            return self._texts.alternative("excluded_road_sensitive")
        if assessment.entry is None and species.coniferous:
            return self._texts.alternative("excluded_conifer", category=self._category.name_ru)
        return None

    def note_reasons(self, assessment: TerritoryAssessment | None) -> list[SelectionReason]:
        if assessment is None or assessment.entry is None:
            return []
        return [self._note_reason(number) for number in assessment.entry.notes if number in EXPLAINED_NOTES]

    def _note_reason(self, number: int) -> SelectionReason:
        note = lowercased(self._official.note_ru(number))
        return self._texts.reason(TERRITORY_SECTION, "official_note", number=number, note=note)

    def composition_reason(self) -> SelectionReason:
        return self._texts.reason(
            TERRITORY_SECTION,
            "composition",
            category=self._category.name_ru,
            composition=self._category.composition_ru,
        )

    def _official_assessment(self, entries: tuple[OfficialEntry, ...]) -> TerritoryAssessment:
        allowed = [entry for entry in entries if self._official_allows(entry)]
        if not allowed:
            return TerritoryAssessment(FORBIDDEN, None, entries[0])
        best = min(allowed, key=lambda entry: entry.level_rank)
        kind = f"{OFFICIAL_KIND_PREFIX}{best.level}"
        reason = self._texts.reason(TERRITORY_SECTION, kind, columns=self._official_columns_ru)
        return TerritoryAssessment(kind, reason, best)

    def _official_allows(self, entry: OfficialEntry) -> bool:
        children_conflict = self._category.children_sensitive and entry.has_note(CHILDREN_NOTE)
        return entry.allows(self._category.official_columns) and not children_conflict

    def _fallback_assessment(self, species: Species) -> TerritoryAssessment:
        verdict = self._catalog.verdict(species.territory_table_name, self._category.tsn_column)
        if verdict is None:
            return TerritoryAssessment(UNLISTED, self._texts.reason(TERRITORY_SECTION, UNLISTED))
        if not verdict.allowed:
            return TerritoryAssessment(FORBIDDEN, None)
        kind = LIMITED if verdict.limited else RECOMMENDED
        return TerritoryAssessment(kind, self._texts.reason(TERRITORY_SECTION, kind, column=self._column_ru))

    def _forbidden_text(self, species: Species) -> str:
        entries = self.official_entries(species)
        if not entries:
            return self._texts.alternative("excluded_territory", column=self._column_ru)
        if self._category.children_sensitive and any(entry.has_note(CHILDREN_NOTE) for entry in entries):
            return self._texts.alternative("excluded_children")
        return self._texts.alternative("excluded_official", columns=self._official_columns_ru)


def lowercased(text: str) -> str:
    return text[:1].lower() + text[1:]
