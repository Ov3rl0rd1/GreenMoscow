from greenplan.knowledge.plant_catalog import STREET_SUITABLE, PlantCatalog, SelectionRule, Species


def species(
    key: str,
    plant_type: str = "tree",
    crown_diameter_m: float = 5.0,
    height_m: float = 10.0,
    *,
    name_ru: str | None = None,
    latin: str = "",
    heating_min_axis_m: float | None = None,
    usage: int = 0,
    crown_class: str | None = None,
    street_suitability: str = STREET_SUITABLE,
) -> Species:
    return Species(
        key=key,
        name_ru=name_ru or key,
        latin=latin,
        plant_type=plant_type,
        crown_diameter_m=crown_diameter_m,
        height_m=height_m,
        crown_class=crown_class,
        heating_min_axis_m=heating_min_axis_m,
        street_suitability=street_suitability,
        reference_usage_total=usage,
    )


def catalog(*items: Species, rules: tuple[SelectionRule, ...] = ()) -> PlantCatalog:
    return PlantCatalog(items, rules)
