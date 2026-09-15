from dataclasses import dataclass
from pathlib import Path

from ezdxf.document import Drawing
from ezdxf.math import Matrix44
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry


@dataclass(frozen=True, slots=True)
class LayerGeometry:
    layer: str
    dxf_type: str
    geometry: BaseGeometry
    source_name: str
    handle: str


@dataclass(frozen=True, slots=True)
class TextAnnotation:
    layer: str
    text: str
    position: Point
    rotation_deg: float
    source_name: str


@dataclass(frozen=True, slots=True)
class BlockReference:
    layer: str
    block_name: str
    position: Point
    scale: float
    rotation_deg: float
    attributes: tuple[tuple[str, str], ...]
    source_name: str

    def attribute(self, tag: str) -> str | None:
        return next((value for key, value in self.attributes if key == tag), None)


@dataclass(frozen=True, slots=True)
class DrawingContent:
    geometries: tuple[LayerGeometry, ...]
    annotations: tuple[TextAnnotation, ...]
    block_references: tuple[BlockReference, ...]

    def layer_names(self) -> set[str]:
        return (
            {item.layer for item in self.geometries}
            | {item.layer for item in self.annotations}
            | {item.layer for item in self.block_references}
        )

    def geometries_on(self, layer: str) -> tuple[LayerGeometry, ...]:
        return tuple(item for item in self.geometries if item.layer == layer)

    def annotations_on(self, layer: str) -> tuple[TextAnnotation, ...]:
        return tuple(item for item in self.annotations if item.layer == layer)


@dataclass(frozen=True, slots=True)
class XrefReference:
    block_name: str
    declared_path: str
    transform: Matrix44


@dataclass(frozen=True, slots=True)
class LoadedDrawing:
    name: str
    path: Path
    document: Drawing
    transform: Matrix44
    is_main: bool


@dataclass(frozen=True, slots=True)
class DrawingSet:
    main: LoadedDrawing
    references: tuple[LoadedDrawing, ...]
    unresolved_references: tuple[str, ...]

    def all_drawings(self) -> tuple[LoadedDrawing, ...]:
        return (self.main, *self.references)
