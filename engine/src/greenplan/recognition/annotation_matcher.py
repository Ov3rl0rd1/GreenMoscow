from collections import defaultdict
from collections.abc import Mapping, Sequence

from shapely.geometry import LineString, MultiLineString, Point
from shapely.strtree import STRtree

from greenplan.domain.drawing import TextAnnotation
from greenplan.recognition.network_annotation_parser import NetworkAnnotation, NetworkAnnotationParser


class AnnotationMatcher:
    def __init__(
        self, parser: NetworkAnnotationParser, match_distance_m: float, leader_tip_match_distance_m: float
    ) -> None:
        self._parser = parser
        self._match_distance_m = match_distance_m
        self._leader_tip_match_distance_m = leader_tip_match_distance_m

    def match(
        self,
        runs: Sequence[LineString | MultiLineString],
        annotations: Sequence[TextAnnotation],
        leader_tips: Mapping[int, Point],
    ) -> dict[int, list[NetworkAnnotation]]:
        if not runs:
            return {}
        tree = STRtree(list(runs))
        matched: dict[int, list[NetworkAnnotation]] = defaultdict(list)
        for annotation_index, annotation in enumerate(annotations):
            parsed = self._parser.parse(annotation.text)
            if parsed is None:
                continue
            anchor, limit = self._anchor(annotation_index, annotation, leader_tips)
            nearest_index = int(tree.nearest(anchor))
            if runs[nearest_index].distance(anchor) <= limit:
                matched[nearest_index].append(parsed)
        return matched

    def _anchor(
        self, annotation_index: int, annotation: TextAnnotation, leader_tips: Mapping[int, Point]
    ) -> tuple[Point, float]:
        if annotation_index in leader_tips:
            return leader_tips[annotation_index], self._leader_tip_match_distance_m
        return annotation.position, self._match_distance_m
