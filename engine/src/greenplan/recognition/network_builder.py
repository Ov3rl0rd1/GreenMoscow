from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import TypeVar

from shapely.geometry import LineString, MultiLineString

from greenplan.domain.drawing import LayerGeometry, TextAnnotation
from greenplan.domain.obstacle_kinds import NETWORK_UNKNOWN
from greenplan.domain.site import Obstacle
from greenplan.geometry.shapes import linear_parts
from greenplan.knowledge.layer_dictionary import LayerClassification
from greenplan.recognition.annotation_matcher import AnnotationMatcher
from greenplan.recognition.dashed_line_stitcher import DashedLineStitcher
from greenplan.recognition.leader_line_detector import LeaderLineDetector
from greenplan.recognition.network_annotation_parser import NetworkAnnotation, NetworkAnnotationParser
from greenplan.recognition.settings import RecognitionSettings

NetworkRun = LineString | MultiLineString
LayeredItem = TypeVar("LayeredItem", LayerGeometry, TextAnnotation)


@dataclass(frozen=True, slots=True)
class _LayerKey:
    layer: str
    source_name: str


class NetworkBuilder:
    def __init__(
        self, leader_detector: LeaderLineDetector, stitcher: DashedLineStitcher, matcher: AnnotationMatcher
    ) -> None:
        self._leader_detector = leader_detector
        self._stitcher = stitcher
        self._matcher = matcher

    @classmethod
    def from_settings(
        cls, parser: NetworkAnnotationParser, settings: RecognitionSettings
    ) -> "NetworkBuilder":
        return cls(
            LeaderLineDetector(
                settings.leader_text_distance_m,
                settings.leader_max_length_m,
                settings.arrow_max_length_m,
                settings.arrow_tip_tolerance_m,
            ),
            DashedLineStitcher(settings.dashed_gap_bridge_m, settings.dashed_alignment_cosine),
            AnnotationMatcher(
                parser, settings.annotation_match_distance_m, settings.leader_tip_match_distance_m
            ),
        )

    def build(
        self,
        geometries: Sequence[LayerGeometry],
        annotations: Sequence[TextAnnotation],
        classifications: dict[str, LayerClassification],
    ) -> tuple[Obstacle, ...]:
        annotations_by_key = _group_by_key(annotations)
        obstacles: list[Obstacle] = []
        for key, items in _group_by_key(geometries).items():
            obstacles.extend(
                self._layer_obstacles(key, items, annotations_by_key.get(key, []), classifications[key.layer])
            )
        return tuple(obstacles)

    def _layer_obstacles(
        self,
        key: _LayerKey,
        items: Sequence[LayerGeometry],
        annotations: Sequence[TextAnnotation],
        classification: LayerClassification,
    ) -> list[Obstacle]:
        lines = [line for item in items for line in linear_parts(item.geometry) if line.length > 0]
        leaders = self._leader_detector.detect(lines, annotations)
        network_lines = [line for index, line in enumerate(lines) if index not in leaders.leader_line_indices]
        runs = self._stitcher.stitch(network_lines)
        matched = self._matcher.match(runs, annotations, leaders.tip_by_annotation)
        return [_obstacle(key, run, matched.get(index, []), classification) for index, run in enumerate(runs)]


def _group_by_key(items: Iterable[LayeredItem]) -> dict[_LayerKey, list[LayeredItem]]:
    grouped: dict[_LayerKey, list[LayeredItem]] = defaultdict(list)
    for item in items:
        grouped[_LayerKey(item.layer, item.source_name)].append(item)
    return grouped


def _obstacle(
    key: _LayerKey,
    run: NetworkRun,
    annotations: Sequence[NetworkAnnotation],
    classification: LayerClassification,
) -> Obstacle:
    widths = [annotation.outer_width_m for annotation in annotations if annotation.outer_width_m is not None]
    evidence = classification.evidence + tuple(f"annotation:{annotation.text}" for annotation in annotations)
    return Obstacle(
        kind=classification.kind or NETWORK_UNKNOWN,
        geometry=run,
        layer=key.layer,
        source_name=key.source_name,
        evidence=evidence,
        outer_radius_m=max(widths) / 2 if widths else None,
        status=classification.status,
        confidence=classification.confidence,
    )
