from pathlib import Path

import pytest

from greenplan.domain.site import BOUNDARY_GAP_CLOSED, BOUNDARY_PIECES_JOINED
from greenplan.recognition.site_boundary_extractor import WORK_BOUNDARY_SOURCE
from greenplan.recognition.site_model_builder import SiteModelBuilder

from fixtures.pilot_objects import load_pilot_object

pytestmark = [pytest.mark.realdata, pytest.mark.converter, pytest.mark.slow]

UNCLOSED_BOUNDARIES = [
    (
        Path("1. Олимпийская деревня")
        / "Исходные данные"
        / "10000176_Генплан_Олимп - Standard"
        / "ссылки"
        / "10000176_Границы работ_Олимп.dwg",
        BOUNDARY_PIECES_JOINED,
    ),
    (
        Path("17. Грузинская М ул") / "Проектное решение" / "xref" / "xref_граница.dwg",
        BOUNDARY_GAP_CLOSED,
    ),
]


@pytest.mark.parametrize(("relative_path", "expected_repair"), UNCLOSED_BOUNDARIES)
def test_unclosed_dataset_boundaries_are_repaired(
    pilot_objects_root: Path,
    dwg2dxf_path: Path,
    repository_root: Path,
    knowledge_root: Path,
    relative_path: Path,
    expected_repair: str,
) -> None:
    loaded = load_pilot_object(pilot_objects_root, relative_path, dwg2dxf_path, repository_root)
    site = SiteModelBuilder.from_knowledge(knowledge_root).build(loaded.content)
    assert site.diagnostics.boundary_source == WORK_BOUNDARY_SOURCE
    assert site.boundary.area > 10_000
    assert expected_repair in {repair.code for repair in site.diagnostics.boundary_repairs}
