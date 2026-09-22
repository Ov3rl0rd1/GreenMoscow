from dataclasses import dataclass

from greenplan.knowledge.plant_catalog import Species
from greenplan.knowledge.territory_catalog import TerritoryCatalog, TerritoryCategory
from greenplan.species.selection_texts import SelectionReason, SelectionTexts
from greenplan.species.site_context import STREET_CARRIAGEWAY_ADJACENT, PlantingContext

RECOMMENDED = "recommended"
LIMITED = "limited"
UNLISTED = "unlisted"
FORBIDDEN = "forbidden"
TERRITORY_SECTION = "territory"


@dataclass(frozen=True, slots=True)
class TerritoryAssessment:
    kind: str
    reason: SelectionReason | None

    @property
    def admissible(self) -> bool:
        return self.kind != FORBIDDEN


class TerritoryPolicy:
    def __init__(self, catalog: TerritoryCatalog, category: TerritoryCategory, texts: SelectionTexts) -> None:
        self._catalog = catalog
        self._category = category
        self._texts = texts
        self._column_ru = catalog.column_ru(category.tsn_column)

    @property
    def category(self) -> TerritoryCategory:
        return self._category

    def assess(self, species: Species) -> TerritoryAssessment:
        verdict = self._catalog.verdict(species.territory_table_name, self._category.tsn_column)
        if verdict is None:
            return TerritoryAssessment(UNLISTED, self._texts.reason(TERRITORY_SECTION, UNLISTED))
        if not verdict.allowed:
            return TerritoryAssessment(FORBIDDEN, None)
        kind = LIMITED if verdict.limited else RECOMMENDED
        return TerritoryAssessment(kind, self._texts.reason(TERRITORY_SECTION, kind, column=self._column_ru))

    def excludes_conifer(self, species: Species, context: PlantingContext) -> bool:
        return (
            species.coniferous
            and not self._category.conifers_near_carriageway
            and STREET_CARRIAGEWAY_ADJACENT in context.tags
        )

    def exclusion_text(self, species: Species) -> str | None:
        if not self.assess(species).admissible:
            return self._texts.alternative("excluded_territory", column=self._column_ru)
        if species.coniferous and not self._category.conifers_near_carriageway:
            return self._texts.alternative("excluded_conifer", category=self._category.name_ru)
        return None

    def composition_reason(self) -> SelectionReason:
        return self._texts.reason(
            TERRITORY_SECTION,
            "composition",
            category=self._category.name_ru,
            composition=self._category.composition_ru,
        )
