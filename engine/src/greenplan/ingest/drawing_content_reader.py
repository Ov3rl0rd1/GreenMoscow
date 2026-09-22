from dataclasses import dataclass, field

from ezdxf.entities import DXFGraphic

from greenplan.domain.drawing import (
    BlockReference,
    DrawingContent,
    DrawingSet,
    LayerGeometry,
    LoadedDrawing,
    TextAnnotation,
)
from greenplan.domain.text_repair import repaired_text
from greenplan.ingest.entity_geometry import (
    BlockReferenceExtractor,
    EntityGeometryExtractor,
    TextAnnotationExtractor,
)

TEXT_ENTITY_TYPES = frozenset({"TEXT", "MTEXT"})


@dataclass
class _ContentAccumulator:
    geometries: list[LayerGeometry] = field(default_factory=list)
    annotations: list[TextAnnotation] = field(default_factory=list)
    block_references: list[BlockReference] = field(default_factory=list)

    def to_content(self) -> DrawingContent:
        return DrawingContent(tuple(self.geometries), tuple(self.annotations), tuple(self.block_references))


class DrawingContentReader:
    def __init__(
        self,
        geometry_extractor: EntityGeometryExtractor | None = None,
        annotation_extractor: TextAnnotationExtractor | None = None,
        block_reference_extractor: BlockReferenceExtractor | None = None,
    ) -> None:
        self._geometry_extractor = geometry_extractor or EntityGeometryExtractor()
        self._annotation_extractor = annotation_extractor or TextAnnotationExtractor()
        self._block_reference_extractor = block_reference_extractor or BlockReferenceExtractor()

    def read(self, drawing_set: DrawingSet) -> DrawingContent:
        accumulator = _ContentAccumulator()
        for drawing in drawing_set.all_drawings():
            self._read_drawing(drawing, accumulator)
        return accumulator.to_content()

    def _read_drawing(self, drawing: LoadedDrawing, accumulator: _ContentAccumulator) -> None:
        xref_block_names = {block.name for block in drawing.document.blocks if block.block_record.is_xref}
        for entity in drawing.document.modelspace():
            self._read_entity(entity, drawing, xref_block_names, accumulator)

    def _read_entity(
        self,
        entity: DXFGraphic,
        drawing: LoadedDrawing,
        xref_block_names: set[str],
        accumulator: _ContentAccumulator,
    ) -> None:
        entity_type = entity.dxftype()
        if entity_type in TEXT_ENTITY_TYPES:
            self._collect_annotation(entity, drawing, accumulator)
        elif entity_type == "INSERT":
            self._collect_block_reference(entity, drawing, xref_block_names, accumulator)
        else:
            self._collect_geometry(entity, drawing, accumulator)

    def _collect_annotation(
        self, entity: DXFGraphic, drawing: LoadedDrawing, accumulator: _ContentAccumulator
    ) -> None:
        annotation = self._annotation_extractor.extract(entity, drawing.transform, drawing.name)
        if annotation is not None:
            accumulator.annotations.append(annotation)

    def _collect_block_reference(
        self,
        entity: DXFGraphic,
        drawing: LoadedDrawing,
        xref_block_names: set[str],
        accumulator: _ContentAccumulator,
    ) -> None:
        if entity.dxf.name in xref_block_names:
            return
        reference = self._block_reference_extractor.extract(entity, drawing.transform, drawing.name)
        accumulator.block_references.append(reference)

    def _collect_geometry(
        self, entity: DXFGraphic, drawing: LoadedDrawing, accumulator: _ContentAccumulator
    ) -> None:
        geometry = self._geometry_extractor.extract(entity, drawing.transform)
        if geometry is None:
            return
        accumulator.geometries.append(
            LayerGeometry(
                repaired_text(entity.dxf.layer),
                entity.dxftype(),
                geometry,
                drawing.name,
                entity.dxf.handle,
            )
        )
