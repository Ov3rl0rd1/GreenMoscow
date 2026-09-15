from shapely.geometry import LineString, Point

from greenplan.domain.drawing import TextAnnotation
from greenplan.recognition.leader_line_detector import LeaderLineDetector
from greenplan.recognition.settings import RecognitionSettings

SETTINGS = RecognitionSettings()
DETECTOR = LeaderLineDetector(
    SETTINGS.leader_text_distance_m,
    SETTINGS.leader_max_length_m,
    SETTINGS.arrow_max_length_m,
    SETTINGS.arrow_tip_tolerance_m,
)
PIPE = LineString([(0, 0), (40, 0)])


def leader_to(tip_x: float, shelf_y: float) -> list[LineString]:
    return [
        LineString([(tip_x - 10, shelf_y), (tip_x - 4, shelf_y), (tip_x, 0)]),
        LineString([(tip_x, 0), (tip_x - 0.65, 0.55)]),
        LineString([(tip_x, 0), (tip_x - 0.05, 0.85)]),
    ]


def label(text: str, x: float, y: float) -> TextAnnotation:
    return TextAnnotation("Газопровод", text, Point(x, y), 0.0, "tile_up")


def test_leader_with_arrow_is_detected_and_tip_is_assigned_to_label() -> None:
    detection = DETECTOR.detect([PIPE, *leader_to(14, 8)], [label("d=219н.д.ст.", 4.2, 8.25)])
    assert detection.leader_line_indices == frozenset({1, 2, 3})
    assert detection.tip_by_annotation[0].equals(Point(14, 0))


def test_leader_with_label_at_bend_and_shelf_to_the_right_is_detected() -> None:
    leader = LineString([(24, 8), (16, 8), (14, 0)])
    wings = [LineString([(14, 0), (14.05, 0.85)]), LineString([(14, 0), (13.4, 0.5)])]
    detection = DETECTOR.detect([PIPE, leader, *wings], [label("146.87в.тр.", 16.0, 8.3)])
    assert detection.leader_line_indices == frozenset({1, 2, 3})
    assert detection.tip_by_annotation[0].equals(Point(14, 0))


def test_line_without_arrow_is_not_a_leader() -> None:
    detection = DETECTOR.detect([PIPE, leader_to(14, 8)[0]], [label("d=219н.д.ст.", 4.2, 8.25)])
    assert detection.leader_line_indices == frozenset()


def test_arrow_line_without_label_at_tail_is_not_a_leader() -> None:
    detection = DETECTOR.detect([PIPE, *leader_to(14, 8)], [label("d=219н.д.ст.", 30, 20)])
    assert detection.leader_line_indices == frozenset()


def test_label_near_arrow_tip_does_not_turn_line_into_leader() -> None:
    detection = DETECTOR.detect([PIPE, *leader_to(14, 8)], [label("d=219н.д.ст.", 13.6, 0.3)])
    assert detection.tip_by_annotation == {}


def test_each_label_takes_leader_with_nearest_shelf() -> None:
    lines = [PIPE, *leader_to(14, 8), *leader_to(24, 9.5)]
    labels = [label("d=219н.д.ст.", 4.2, 8.25), label("165.80в.тр.", 14.2, 9.75)]
    detection = DETECTOR.detect(lines, labels)
    assert detection.tip_by_annotation[0].equals(Point(14, 0))
    assert detection.tip_by_annotation[1].equals(Point(24, 0))
