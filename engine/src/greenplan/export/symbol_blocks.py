from ezdxf.document import Drawing
from ezdxf.layouts import BlockLayout

from greenplan.explain.explanation_model import PlantExplanation
from greenplan.export.export_settings import ExportSettings
from greenplan.export.layer_names import LayerNameSanitizer

BLOCK_BASE_LAYER = "0"
REJECTION_SYMBOL_NAME = "REJECTED"


class SymbolBlockFactory:
    def __init__(
        self,
        document: Drawing,
        settings: ExportSettings,
        sanitizer: LayerNameSanitizer,
        trunk_diameter_m: float,
    ) -> None:
        self._document = document
        self._settings = settings
        self._sanitizer = sanitizer
        self._trunk_diameter_m = trunk_diameter_m
        self._created: set[str] = set()

    def plant_block(self, plant: PlantExplanation) -> str:
        species_key = plant.species.key if plant.species else plant.plant_type
        name = self._block_name(plant.plant_type, species_key)
        if name not in self._created:
            self._create_plant_block(name, plant.crown_diameter_m)
        return name

    def rejection_block(self) -> str:
        name = self._block_name(REJECTION_SYMBOL_NAME)
        if name not in self._created:
            self._create_rejection_block(name)
        return name

    def _block_name(self, *parts: str) -> str:
        return self._sanitizer.join(self._settings.layer_prefix, self._settings.symbol_block_stem, *parts)

    def _create_plant_block(self, name: str, crown_diameter_m: float) -> None:
        block = self._document.blocks.new(name)
        crown_radius = crown_diameter_m / 2
        block.add_circle((0, 0), crown_radius, dxfattribs={"layer": BLOCK_BASE_LAYER})
        block.add_circle((0, 0), self._trunk_diameter_m / 2, dxfattribs={"layer": BLOCK_BASE_LAYER})
        self._add_identity_attribute(block, (crown_radius, crown_radius))
        self._created.add(name)

    def _create_rejection_block(self, name: str) -> None:
        block = self._document.blocks.new(name)
        half = self._settings.rejection_marker_size_m / 2
        block.add_line((-half, -half), (half, half), dxfattribs={"layer": BLOCK_BASE_LAYER})
        block.add_line((-half, half), (half, -half), dxfattribs={"layer": BLOCK_BASE_LAYER})
        self._add_identity_attribute(block, (half, half))
        self._created.add(name)

    def _add_identity_attribute(self, block: BlockLayout, position: tuple[float, float]) -> None:
        block.add_attdef(
            self._settings.id_attribute_tag,
            position,
            dxfattribs={"layer": BLOCK_BASE_LAYER, "height": self._settings.label_height_m},
        )
