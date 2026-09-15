import math
from functools import reduce

from ezdxf import path as dxf_path
from ezdxf.entities import DXFGraphic
from ezdxf.math import Matrix44, Vec3
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.validation import make_valid

from greenplan.domain.drawing import BlockReference, TextAnnotation

DEFAULT_MAX_SAGITTA_M = 0.05
MINIMUM_RING_POINTS = 3
MINIMUM_LINE_POINTS = 2
CURVE_ENTITY_TYPES = frozenset({"LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "ELLIPSE", "SPLINE"})


class EntityGeometryExtractor:
    def __init__(self, max_sagitta_m: float = DEFAULT_MAX_SAGITTA_M) -> None:
        self._max_sagitta_m = max_sagitta_m

    def extract(self, entity: DXFGraphic, transform: Matrix44) -> BaseGeometry | None:
        entity_type = entity.dxftype()
        if entity_type in CURVE_ENTITY_TYPES:
            return self._curve(entity, transform)
        if entity_type == "HATCH":
            return self._hatch_area(entity, transform)
        if entity_type == "POINT":
            return Point(transform.transform(entity.dxf.location).vec2)
        return None

    def _curve(self, entity: DXFGraphic, transform: Matrix44) -> LineString | None:
        try:
            curve = dxf_path.make_path(entity).transform(transform)
        except (TypeError, ValueError):
            return None
        coordinates = self._planar_coordinates(curve.flattening(self._max_sagitta_m))
        return LineString(coordinates) if len(coordinates) >= MINIMUM_LINE_POINTS else None

    def _hatch_area(self, entity: DXFGraphic, transform: Matrix44) -> BaseGeometry | None:
        rings = [self._ring(boundary.transform(transform)) for boundary in dxf_path.from_hatch(entity)]
        polygons = [ring for ring in rings if ring is not None]
        if not polygons:
            return None
        combined = reduce(lambda accumulated, polygon: accumulated.symmetric_difference(polygon), polygons)
        return None if combined.is_empty else combined

    def _ring(self, boundary: dxf_path.Path) -> Polygon | None:
        coordinates = self._planar_coordinates(boundary.flattening(self._max_sagitta_m))
        if len(coordinates) < MINIMUM_RING_POINTS:
            return None
        polygon = make_valid(Polygon(coordinates))
        return polygon if polygon.area > 0 else None

    def _planar_coordinates(self, vertices: "list[Vec3] | object") -> list[tuple[float, float]]:
        coordinates: list[tuple[float, float]] = []
        for vertex in vertices:
            point = (vertex.x, vertex.y)
            if not coordinates or coordinates[-1] != point:
                coordinates.append(point)
        return coordinates


class TextAnnotationExtractor:
    def extract(self, entity: DXFGraphic, transform: Matrix44, source_name: str) -> TextAnnotation | None:
        text = self._plain_text(entity).strip()
        if not text:
            return None
        position = transform.transform(entity.dxf.insert)
        rotation = self._entity_rotation(entity) + transform_rotation_deg(transform)
        return TextAnnotation(
            entity.dxf.layer, text, Point(position.x, position.y), rotation % 360.0, source_name
        )

    def _plain_text(self, entity: DXFGraphic) -> str:
        return entity.plain_text() if entity.dxftype() == "MTEXT" else entity.dxf.text

    def _entity_rotation(self, entity: DXFGraphic) -> float:
        return entity.get_rotation() if entity.dxftype() == "MTEXT" else entity.dxf.rotation


class BlockReferenceExtractor:
    def extract(self, insert: DXFGraphic, transform: Matrix44, source_name: str) -> BlockReference:
        position = transform.transform(insert.dxf.insert)
        attributes = tuple((attribute.dxf.tag, attribute.dxf.text) for attribute in insert.attribs)
        return BlockReference(
            layer=insert.dxf.layer,
            block_name=insert.dxf.name,
            position=Point(position.x, position.y),
            scale=abs(insert.dxf.xscale) * transform_scale(transform),
            rotation_deg=(insert.dxf.rotation + transform_rotation_deg(transform)) % 360.0,
            attributes=attributes,
            source_name=source_name,
        )


def transform_rotation_deg(transform: Matrix44) -> float:
    axis = transform.ux
    return math.degrees(math.atan2(axis.y, axis.x))


def transform_scale(transform: Matrix44) -> float:
    return transform.ux.magnitude
