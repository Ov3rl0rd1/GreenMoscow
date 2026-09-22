from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from greenplan.domain.errors import ConfigurationError, KnowledgeValidationError
from greenplan.knowledge.yaml_loader import load_yaml_mapping, require_key

ALLOWED_MARK = "+"
LIMITED_MARKER = "огр"
NAME_FIELD = "name_ru"


@dataclass(frozen=True, slots=True)
class TerritoryVerdict:
    cell: str

    @property
    def allowed(self) -> bool:
        return self.cell.strip().startswith(ALLOWED_MARK)

    @property
    def limited(self) -> bool:
        return LIMITED_MARKER in self.cell


@dataclass(frozen=True, slots=True)
class TerritoryCategory:
    category_id: str
    name_ru: str
    tsn_column: str
    density_context: str
    conifers_near_carriageway: bool
    noise_protection: bool
    composition_ru: str


class TerritoryCatalog:
    def __init__(
        self,
        categories: Sequence[TerritoryCategory],
        default_id: str,
        table: Mapping[str, Mapping[str, str]],
        column_names: Mapping[str, str],
        source_ref: str,
    ) -> None:
        self._categories = {category.category_id: category for category in categories}
        self._default_id = default_id
        self._table = {normalized(name): dict(cells) for name, cells in table.items()}
        self._column_names = dict(column_names)
        self.source_ref = source_ref
        self._validate()

    @classmethod
    def from_knowledge(cls, knowledge_root: Path) -> "TerritoryCatalog":
        plants = knowledge_root / "plants"
        categories_path = plants / "territory_categories.yaml"
        table_path = plants / "territory_suitability.yaml"
        categories = load_yaml_mapping(categories_path)
        table = load_yaml_mapping(table_path)
        table_meta = require_key(table, "meta", table_path)
        columns = require_key(table_meta, "columns", table_path)
        return cls(
            categories=[
                _category_from(entry) for entry in require_key(categories, "categories", categories_path)
            ],
            default_id=require_key(
                require_key(categories, "meta", categories_path), "default", categories_path
            ),
            table={
                row[NAME_FIELD]: {column: row[column] for column in columns} for row in table["species"]
            },
            column_names=columns,
            source_ref=require_key(table_meta, "source_ref", table_path),
        )

    @property
    def default_id(self) -> str:
        return self._default_id

    def categories(self) -> tuple[TerritoryCategory, ...]:
        return tuple(self._categories.values())

    def category(self, category_id: str | None) -> TerritoryCategory:
        chosen = category_id or self._default_id
        if chosen not in self._categories:
            known = ", ".join(sorted(self._categories))
            raise ConfigurationError(f"неизвестная категория территории '{chosen}'; допустимы: {known}")
        return self._categories[chosen]

    def verdict(self, table_name: str | None, column: str) -> TerritoryVerdict | None:
        if not table_name:
            return None
        row = self._table.get(normalized(table_name))
        return TerritoryVerdict(row[column]) if row is not None else None

    def column_ru(self, column: str) -> str:
        return self._column_names[column]

    def _validate(self) -> None:
        if self._default_id not in self._categories:
            raise KnowledgeValidationError(f"default territory category '{self._default_id}' is not defined")
        unknown = sorted(
            category.category_id
            for category in self._categories.values()
            if category.tsn_column not in self._column_names
        )
        if unknown:
            raise KnowledgeValidationError(f"territory categories with unknown table column: {unknown}")


def normalized(name: str) -> str:
    return " ".join(name.lower().replace("ё", "е").split())


def _category_from(entry: Mapping[str, Any]) -> TerritoryCategory:
    return TerritoryCategory(
        category_id=entry["id"],
        name_ru=entry["name_ru"],
        tsn_column=entry["tsn_column"],
        density_context=entry["density_context"],
        conifers_near_carriageway=bool(entry.get("conifers_near_carriageway", True)),
        noise_protection=bool(entry.get("noise_protection", False)),
        composition_ru=(entry.get("composition_ru") or "").strip(),
    )
