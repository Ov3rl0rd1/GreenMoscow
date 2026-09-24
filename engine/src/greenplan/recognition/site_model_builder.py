from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from shapely.geometry import LineString, MultiPolygon, Polygon

from greenplan.domain.drawing import DrawingContent, LayerGeometry
from greenplan.domain.obstacle_kinds import (
    BUILDING_WALL,
    CARRIAGEWAY_EDGE,
    CURB,
    EDGE_KINDS,
    POINT_SYMBOL_KINDS,
    SIDEWALK_EDGE,
    STREET_AXIS,
    UNDERGROUND_NETWORK_KINDS,
)
from greenplan.domain.site import (
    BUILDINGS_NOT_FOUND,
    NETWORKS_NOT_FOUND,
    PLANTING_AREA_NOT_FOUND,
    PROJECTED_STATUS,
    PROTECTED_AREAS_NOT_CHECKED,
    Obstacle,
    SiteDiagnostics,
    SiteModel,
)
from greenplan.geometry.ring_assembler import RingAssembler
from greenplan.geometry.shapes import linear_parts, polygonal_parts
from greenplan.knowledge.layer_dictionary import LayerClassification, LayerDictionary
from greenplan.knowledge.surface_codes import SurfaceCodeCatalog
from greenplan.recognition.existing_tree_extractor import ExistingTreeExtractor
from greenplan.recognition.network_annotation_parser import NetworkAnnotationParser
from greenplan.recognition.network_builder import NetworkBuilder
from greenplan.recognition.settings import RecognitionSettings
from greenplan.recognition.site_boundary_extractor import (
    CONTENT_EXTENT_SOURCE,
    SiteBoundary,
    SiteBoundaryExtractor,
)
from greenplan.recognition.surface_classifier import SurfaceClassifier, SurfaceMap
from greenplan.recognition.symbol_clusterer import SymbolClusterer

SURFACE_EDGE_SOURCE = "surface_edges"


class SiteModelBuilder:
    def __init__(
        self,
        dictionary: LayerDictionary,
        surface_classifier: SurfaceClassifier,
        network_builder: NetworkBuilder,
        boundary_extractor: SiteBoundaryExtractor,
        tree_extractor: ExistingTreeExtractor,
        symbol_clusterer: SymbolClusterer,
        settings: RecognitionSettings,
    ) -> None:
        self._dictionary = dictionary
        self._surface_classifier = surface_classifier
        self._network_builder = network_builder
        self._boundary_extractor = boundary_extractor
        self._tree_extractor = tree_extractor
        self._symbol_clusterer = symbol_clusterer
        self._settings = settings

    @classmethod
    def from_knowledge(
        cls, knowledge_root: Path, settings: RecognitionSettings | None = None
    ) -> "SiteModelBuilder":
        effective = settings or RecognitionSettings()
        layers_file = knowledge_root / "dataset" / "mosgeotrest_layers.yaml"
        clusterer = SymbolClusterer(effective.symbol_cluster_gap_m, effective.max_symbol_size_m)
        return cls(
            dictionary=LayerDictionary.from_file(layers_file),
            surface_classifier=SurfaceClassifier(
                SurfaceCodeCatalog.from_file(knowledge_root / "dataset" / "surface_codes.yaml")
            ),
            network_builder=NetworkBuilder.from_settings(
                NetworkAnnotationParser.from_file(layers_file), effective
            ),
            boundary_extractor=SiteBoundaryExtractor(
                effective.minimum_boundary_area_m2,
                RingAssembler(
                    effective.boundary_closure_tolerance_m,
                    effective.boundary_contact_tolerance_m,
                    effective.boundary_relative_closure_fraction,
                ),
            ),
            tree_extractor=ExistingTreeExtractor(clusterer, effective.survey_coverage_radius_m),
            symbol_clusterer=clusterer,
            settings=effective,
        )

    def build(self, content: DrawingContent, unresolved_references: Sequence[str] = ()) -> SiteModel:
        classifications = {layer: self._dictionary.classify(layer) for layer in content.layer_names()}
        boundary = self._boundary_extractor.extract(content.geometries, classifications)
        surfaces = self._surface_classifier.classify(content.geometries)
        obstacles = self._collect_obstacles(content, classifications, surfaces)
        trees = self._tree_extractor.extract(content.geometries, content.block_references, classifications)
        plantable = plantable_surface(surfaces, boundary)
        diagnostics = self._diagnostics(
            classifications, obstacles, unresolved_references, boundary, surfaces, plantable.is_empty
        )
        return SiteModel(
            boundary=boundary.area,
            plantable_surface=_as_areal(plantable),
            obstacles=obstacles,
            existing_trees=trees,
            street_axes=self._street_axes(content.geometries, classifications),
            diagnostics=diagnostics,
        )

    def _collect_obstacles(
        self, content: DrawingContent, classifications: dict[str, LayerClassification], surfaces: SurfaceMap
    ) -> tuple[Obstacle, ...]:
        networks = self._network_builder.build(
            self._geometries_of_kinds(content.geometries, classifications, UNDERGROUND_NETWORK_KINDS),
            content.annotations,
            classifications,
        )
        return (
            tuple(obstacle for obstacle in networks if self._is_network_included(obstacle))
            + self._point_obstacles(content, classifications)
            + self._edge_obstacles(content.geometries, classifications, surfaces)
        )

    def _is_network_included(self, obstacle: Obstacle) -> bool:
        return self._settings.include_projected_networks or obstacle.status != PROJECTED_STATUS

    def _geometries_of_kinds(
        self,
        geometries: Sequence[LayerGeometry],
        classifications: dict[str, LayerClassification],
        kinds: frozenset[str],
    ) -> list[LayerGeometry]:
        return [item for item in geometries if classifications[item.layer].kind in kinds]

    def _point_obstacles(
        self, content: DrawingContent, classifications: dict[str, LayerClassification]
    ) -> tuple[Obstacle, ...]:
        obstacles: list[Obstacle] = []
        for reference in content.block_references:
            classification = classifications[reference.layer]
            if classification.kind in POINT_SYMBOL_KINDS:
                obstacles.append(_obstacle_from(classification, reference.position, reference.source_name))
        symbol_geometries = self._geometries_of_kinds(content.geometries, classifications, POINT_SYMBOL_KINDS)
        for (layer, source_name), items in _group_by_layer_and_source(symbol_geometries).items():
            positions = self._symbol_clusterer.symbol_positions([item.geometry for item in items])
            obstacles.extend(
                _obstacle_from(classifications[layer], position, source_name) for position in positions
            )
        return tuple(obstacles)

    def _edge_obstacles(
        self,
        geometries: Sequence[LayerGeometry],
        classifications: dict[str, LayerClassification],
        surfaces: SurfaceMap,
    ) -> tuple[Obstacle, ...]:
        surface_edges = self._surface_edges(surfaces)
        replaced_kinds = {obstacle.kind for obstacle in surface_edges} | ({CURB} if surface_edges else set())
        drawn_edges = tuple(
            _obstacle_from(classifications[item.layer], item.geometry, item.source_name)
            for item in geometries
            if self._is_drawn_edge(classifications[item.layer], replaced_kinds)
        )
        return surface_edges + drawn_edges

    def _is_drawn_edge(self, classification: LayerClassification, replaced_kinds: set[str]) -> bool:
        kind = CARRIAGEWAY_EDGE if classification.kind == CURB else classification.kind
        return kind in EDGE_KINDS and kind not in replaced_kinds and classification.kind not in replaced_kinds

    def _surface_edges(self, surfaces: SurfaceMap) -> tuple[Obstacle, ...]:
        edges: list[Obstacle] = []
        for kind, area in ((CARRIAGEWAY_EDGE, surfaces.carriageway), (SIDEWALK_EDGE, surfaces.sidewalk)):
            for polygon in polygonal_parts(area):
                evidence = (f"surface:{kind}", "source:project_surfaces")
                edges.append(Obstacle(kind, polygon.exterior, "surfaces", SURFACE_EDGE_SOURCE, evidence))
        return tuple(edges)

    def _street_axes(
        self, geometries: Sequence[LayerGeometry], classifications: dict[str, LayerClassification]
    ) -> tuple[LineString, ...]:
        return tuple(
            line
            for item in geometries
            if classifications[item.layer].kind == STREET_AXIS
            for line in linear_parts(item.geometry)
        )

    def _diagnostics(
        self,
        classifications: dict[str, LayerClassification],
        obstacles: Sequence[Obstacle],
        unresolved_references: Sequence[str],
        boundary: SiteBoundary,
        surfaces: SurfaceMap,
        nothing_to_plant: bool,
    ) -> SiteDiagnostics:
        networks = [obstacle for obstacle in obstacles if obstacle.kind in UNDERGROUND_NETWORK_KINDS]
        total_length = sum(obstacle.geometry.length for obstacle in networks)
        annotated_length = sum(
            obstacle.geometry.length for obstacle in networks if obstacle.outer_radius_m is not None
        )
        return SiteDiagnostics(
            obstacle_counts=dict(Counter(obstacle.kind for obstacle in obstacles)),
            unknown_layers=tuple(
                sorted(layer for layer, item in classifications.items() if not item.is_known)
            ),
            unresolved_references=tuple(unresolved_references),
            boundary_source=boundary.source,
            boundary_repairs=boundary.repairs,
            lawn_source=surfaces.lawn_source,
            annotated_network_share=annotated_length / total_length if total_length > 0 else 0.0,
            warnings=site_warnings(obstacles, nothing_to_plant),
        )


def plantable_surface(surfaces: SurfaceMap, boundary: SiteBoundary) -> Polygon | MultiPolygon:
    if not surfaces.lawn.is_empty:
        return surfaces.lawn.intersection(boundary.area)
    if boundary.source == CONTENT_EXTENT_SOURCE:
        return Polygon()
    return boundary.area


def site_warnings(obstacles: Sequence[Obstacle], nothing_to_plant: bool = False) -> tuple[str, ...]:
    kinds = {obstacle.kind for obstacle in obstacles}
    missing = [
        code
        for code, present in (
            (PLANTING_AREA_NOT_FOUND, not nothing_to_plant),
            (NETWORKS_NOT_FOUND, bool(kinds & set(UNDERGROUND_NETWORK_KINDS))),
            (BUILDINGS_NOT_FOUND, BUILDING_WALL in kinds),
        )
        if not present
    ]
    return (*missing, PROTECTED_AREAS_NOT_CHECKED)


def _obstacle_from(classification: LayerClassification, geometry, source_name: str) -> Obstacle:
    kind = CARRIAGEWAY_EDGE if classification.kind == CURB else classification.kind
    return Obstacle(
        kind=kind,
        geometry=geometry,
        layer=classification.layer,
        source_name=source_name,
        evidence=classification.evidence,
        status=classification.status,
        confidence=classification.confidence,
    )


def _group_by_layer_and_source(items: Sequence[LayerGeometry]) -> dict[tuple[str, str], list[LayerGeometry]]:
    grouped: dict[tuple[str, str], list[LayerGeometry]] = {}
    for item in items:
        grouped.setdefault((item.layer, item.source_name), []).append(item)
    return grouped


def _as_areal(geometry) -> Polygon | MultiPolygon:
    parts = polygonal_parts(geometry)
    return parts[0] if len(parts) == 1 else MultiPolygon(parts)
