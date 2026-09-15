from pathlib import Path

import pytest

from greenplan.recognition.site_model_builder import SiteModelBuilder

from fixtures.site_content_factory import synthetic_street_content


@pytest.fixture(scope="module")
def site_model(knowledge_root: Path):
    return SiteModelBuilder.from_knowledge(knowledge_root).build(synthetic_street_content(), ["absent.dwg"])


def test_plantable_surface_is_lawn_inside_boundary(site_model) -> None:
    assert site_model.plantable_surface.area == pytest.approx(1000.0)
    assert site_model.diagnostics.lawn_source == "project_surfaces"
    assert site_model.diagnostics.boundary_source == "work_boundary"


def test_gas_pipeline_pieces_become_one_annotated_obstacle(site_model) -> None:
    gas = site_model.obstacles_of("gas_pipeline")
    assert len(gas) == 1
    assert gas[0].outer_radius_m == pytest.approx(0.055)
    assert site_model.diagnostics.annotated_network_share == pytest.approx(1.0)


def test_carriageway_edge_comes_from_surfaces_not_curb_lines(site_model) -> None:
    edges = site_model.obstacles_of("carriageway_edge")
    assert edges
    assert all(edge.source_name == "surface_edges" for edge in edges)


def test_lamp_symbol_becomes_point_obstacle(site_model) -> None:
    lamps = site_model.obstacles_of("lighting_pole")
    assert len(lamps) == 1
    assert lamps[0].geometry.x == pytest.approx(30.0, abs=0.01)


def test_existing_tree_and_unresolved_references_are_reported(site_model) -> None:
    assert len(site_model.kept_trees()) == 1
    assert site_model.diagnostics.unresolved_references == ("absent.dwg",)
