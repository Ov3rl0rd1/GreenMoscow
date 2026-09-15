from pathlib import Path

import pytest

from greenplan.domain.site import SiteModel
from greenplan.explain.report_builder import ReportBuilder
from greenplan.explain.report_model import PlantingReport
from greenplan.placement.planting_plan import PlantingPlan, PlantingPlanComposer
from greenplan.recognition.site_model_builder import SiteModelBuilder
from greenplan.species.species_selector import SpeciesOutcome, SpeciesSelectorFactory

from fixtures.pilot_objects import BAGRITSKOGO_MAIN, LoadedPilotObject, load_pilot_object


@pytest.fixture(scope="session")
def bagritskogo(pilot_objects_root: Path, dwg2dxf_path: Path, repository_root: Path) -> LoadedPilotObject:
    return load_pilot_object(pilot_objects_root, BAGRITSKOGO_MAIN, dwg2dxf_path, repository_root)


@pytest.fixture(scope="session")
def bagritskogo_site(bagritskogo: LoadedPilotObject, knowledge_root: Path) -> SiteModel:
    builder = SiteModelBuilder.from_knowledge(knowledge_root)
    return builder.build(bagritskogo.content, bagritskogo.drawing_set.unresolved_references)


@pytest.fixture(scope="session")
def bagritskogo_plan(bagritskogo_site: SiteModel, knowledge_root: Path) -> PlantingPlan:
    return PlantingPlanComposer.from_knowledge(knowledge_root).compose(bagritskogo_site)


@pytest.fixture(scope="session")
def bagritskogo_species(
    bagritskogo_site: SiteModel, bagritskogo_plan: PlantingPlan, knowledge_root: Path
) -> SpeciesOutcome:
    selector = SpeciesSelectorFactory.from_knowledge(knowledge_root).for_site(bagritskogo_site)
    return selector.assign(bagritskogo_plan.trees + bagritskogo_plan.shrubs)


@pytest.fixture(scope="session")
def bagritskogo_report(
    bagritskogo_site: SiteModel,
    bagritskogo_plan: PlantingPlan,
    bagritskogo_species: SpeciesOutcome,
    knowledge_root: Path,
) -> PlantingReport:
    builder = ReportBuilder.from_knowledge(knowledge_root)
    return builder.build("Улица Багрицкого", bagritskogo_site, bagritskogo_plan, bagritskogo_species)
