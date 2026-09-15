from pathlib import Path

import pytest
from shapely.geometry import LineString, Point

from greenplan.domain.drawing import LayerGeometry, TextAnnotation
from greenplan.knowledge.layer_dictionary import LayerDictionary
from greenplan.recognition.network_annotation_parser import NetworkAnnotationParser
from greenplan.recognition.network_builder import NetworkBuilder
from greenplan.recognition.settings import RecognitionSettings


@pytest.fixture(scope="module")
def layers_file(knowledge_root: Path) -> Path:
    return knowledge_root / "dataset" / "mosgeotrest_layers.yaml"


@pytest.fixture(scope="module")
def parser(layers_file: Path) -> NetworkAnnotationParser:
    return NetworkAnnotationParser.from_file(layers_file)


@pytest.fixture(scope="module")
def dictionary(layers_file: Path) -> LayerDictionary:
    return LayerDictionary.from_file(layers_file)


@pytest.mark.parametrize(
    ("text", "expected_width_m"),
    [
        ("d=300ст.", 0.3),
        ("d=110н.д.п/э", 0.11),
        ("d=219н.д.ст.", 0.219),
        ("d=2х400", 0.8),
        ("d=2x426б.к.", 0.852),
        ("d=2x250 1720х1100", 1.72),
        ("ф-р d=219ст.", 0.219),
        ("ф-р d=2х530ст.", 1.06),
        ("d=1400ж.б.", 1.4),
    ],
)
def test_annotation_outer_width(parser: NetworkAnnotationParser, text: str, expected_width_m: float) -> None:
    assert parser.parse(text).outer_width_m == pytest.approx(expected_width_m)


@pytest.mark.parametrize("text", ["2тр.", "1к.", "каб.", "гидрант", "171.43о.тр."])
def test_texts_without_dimensions_are_not_annotations(parser: NetworkAnnotationParser, text: str) -> None:
    assert parser.parse(text) is None


def gas_piece(start: tuple[float, float], end: tuple[float, float], source: str = "tile_up") -> LayerGeometry:
    return LayerGeometry("Газопровод", "LINE", LineString([start, end]), source, "1")


def build_networks(parser, dictionary, geometries, annotations):
    classifications = {layer: dictionary.classify(layer) for layer in {"Газопровод", "Водопровод"}}
    builder = NetworkBuilder.from_settings(parser, RecognitionSettings())
    return builder.build(geometries, annotations, classifications)


def test_leader_line_is_excluded_and_label_goes_to_pipe_under_arrow(parser, dictionary) -> None:
    pointed_pipe = gas_piece((0, 0), (40, 0))
    crossed_pipe = gas_piece((0, 3), (40, 3))
    leader = LayerGeometry("Газопровод", "LWPOLYLINE", LineString([(4, 8), (10, 8), (14, 0)]), "tile_up", "L")
    wings = [gas_piece((14, 0), (13.35, 0.55)), gas_piece((14, 0), (13.95, 0.85))]
    label = TextAnnotation("Газопровод", "d=219н.д.ст.", Point(4.2, 8.25), 0.0, "tile_up")
    networks = build_networks(parser, dictionary, [pointed_pipe, crossed_pipe, leader, *wings], [label])
    radius_by_y = {round(network.geometry.centroid.y): network.outer_radius_m for network in networks}
    assert len(networks) == 2
    assert all(network.geometry.length == pytest.approx(40.0) for network in networks)
    assert radius_by_y[0] == pytest.approx(0.1095)
    assert radius_by_y[3] is None


def test_annotation_on_one_dash_applies_to_whole_dashed_run(parser, dictionary) -> None:
    pieces = [gas_piece((index * 1.5, 0), (index * 1.5 + 1.0, 0)) for index in range(20)]
    annotation = TextAnnotation("Газопровод", "d=300ст.", Point(1.5, 0.8), 0.0, "tile_up")
    networks = build_networks(parser, dictionary, pieces, [annotation])
    assert len(networks) == 1
    assert networks[0].outer_radius_m == pytest.approx(0.15)
    assert networks[0].geometry.length == pytest.approx(19 * 1.5 + 1.0)


def test_exploded_line_pieces_are_merged_into_one_network(parser, dictionary) -> None:
    networks = build_networks(
        parser, dictionary, [gas_piece((0, 0), (10, 0)), gas_piece((10, 0), (25, 0))], []
    )
    assert len(networks) == 1
    assert networks[0].geometry.length == pytest.approx(25.0)
    assert networks[0].kind == "gas_pipeline"


def test_nearest_annotation_sets_outer_radius(parser, dictionary) -> None:
    annotation = TextAnnotation("Газопровод", "d=219н.д.ст.", Point(5, 1.2), 0.0, "tile_up")
    networks = build_networks(parser, dictionary, [gas_piece((0, 0), (10, 0))], [annotation])
    assert networks[0].outer_radius_m == pytest.approx(0.1095)
    assert "annotation:d=219н.д.ст." in networks[0].evidence


def test_far_annotation_is_not_matched(parser, dictionary) -> None:
    annotation = TextAnnotation("Газопровод", "d=219н.д.ст.", Point(5, 50), 0.0, "tile_up")
    networks = build_networks(parser, dictionary, [gas_piece((0, 0), (10, 0))], [annotation])
    assert networks[0].outer_radius_m is None


def test_annotation_from_other_layer_is_ignored(parser, dictionary) -> None:
    annotation = TextAnnotation("Водопровод", "d=500ст.", Point(5, 0.5), 0.0, "tile_up")
    networks = build_networks(parser, dictionary, [gas_piece((0, 0), (10, 0))], [annotation])
    assert networks[0].outer_radius_m is None


def test_same_layer_from_different_tiles_is_kept_separate(parser, dictionary) -> None:
    pieces = [gas_piece((0, 0), (10, 0), "tile_a"), gas_piece((10, 0), (20, 0), "tile_b")]
    assert len(build_networks(parser, dictionary, pieces, [])) == 2
