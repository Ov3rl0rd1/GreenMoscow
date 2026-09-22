from collections import Counter
from collections.abc import Sequence

from ezdxf.document import Drawing
from ezdxf.entities import Insert
from shapely.geometry import Point

from greenplan.domain.text_repair import repaired_text
from greenplan.export.export_settings import ExportSettings
from greenplan.export.layer_names import SEPARATOR
from greenplan.export.plan_layer_writer import XDATA_EMPTY_VALUE, XDATA_REAL_CODE, XDATA_STRING_CODE
from greenplan.verify.verification_model import (
    DUPLICATE_PLANT_ID,
    FORMAT_SEVERITY,
    MISSING_IDENTITY,
    PlacedPlant,
    VerificationViolation,
)

STATUS_INDEX = 1
PLANT_TYPE_INDEX = 2
SPECIES_INDEX = 3
REQUIRED_STRING_COUNT = 4


class GeneratedPlanReader:
    def __init__(self, settings: ExportSettings) -> None:
        self._settings = settings
        self._plant_prefixes = tuple(
            f"{settings.layer_prefix}{SEPARATOR}{stem}{SEPARATOR}"
            for stem in (settings.tree_layer_stem, settings.shrub_layer_stem)
        )

    def read(self, document: Drawing) -> tuple[list[PlacedPlant], list[VerificationViolation]]:
        plants: list[PlacedPlant] = []
        problems: list[VerificationViolation] = []
        for insert in document.modelspace().query("INSERT"):
            if not insert.dxf.layer.upper().startswith(self._plant_prefixes):
                continue
            plant = self._placed_plant(insert)
            if plant is None:
                problems.append(VerificationViolation(insert.dxf.handle, MISSING_IDENTITY, FORMAT_SEVERITY))
            else:
                plants.append(plant)
        return plants, problems + _duplicate_identifiers(plants)

    def _placed_plant(self, insert: Insert) -> PlacedPlant | None:
        application = self._settings.xdata_application
        identifier = insert.get_attrib_text(self._settings.id_attribute_tag, default="")
        if not identifier or not insert.has_xdata(application):
            return None
        tags = insert.get_xdata(application)
        strings = [str(tag.value) for tag in tags if tag.code == XDATA_STRING_CODE]
        reals = [float(tag.value) for tag in tags if tag.code == XDATA_REAL_CODE]
        if len(strings) < REQUIRED_STRING_COUNT or not reals:
            return None
        position = insert.dxf.insert
        species_key = strings[SPECIES_INDEX]
        return PlacedPlant(
            plant_id=identifier,
            plant_type=strings[PLANT_TYPE_INDEX],
            species_key="" if species_key == XDATA_EMPTY_VALUE else species_key,
            status=strings[STATUS_INDEX],
            position=Point(position.x, position.y),
            crown_diameter_m=reals[0],
            layer=repaired_text(insert.dxf.layer),
            handle=insert.dxf.handle,
        )


def _duplicate_identifiers(plants: Sequence[PlacedPlant]) -> list[VerificationViolation]:
    counts = Counter(plant.plant_id for plant in plants)
    return [
        VerificationViolation(identifier, DUPLICATE_PLANT_ID, FORMAT_SEVERITY)
        for identifier, count in sorted(counts.items())
        if count > 1
    ]
