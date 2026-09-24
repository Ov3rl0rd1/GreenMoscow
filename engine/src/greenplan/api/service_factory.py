from dataclasses import dataclass
from pathlib import Path

from greenplan.api.job_repository import JobRepository
from greenplan.api.job_service import JobService
from greenplan.api.upload_storage import UploadStorage
from greenplan.pipeline.components import PipelineComponents
from greenplan.pipeline.environment import (
    current_timestamp,
    locate_dwg2dxf,
    locate_knowledge_root,
    locate_model,
    resolve_cache_directory,
    resolve_jobs_root,
)
from greenplan.pipeline.planning_pipeline import PlanningPipeline
from greenplan.pipeline.run_config import RunConfig, RunConfigLoader
from greenplan.placement.guidance import GuidanceFactory, rule_guidance


@dataclass(frozen=True, slots=True)
class ServiceLocation:
    jobs_root: Path
    knowledge_root: Path
    cache_directory: Path
    converter: Path | None
    model: Path | None = None

    @classmethod
    def resolve(
        cls,
        jobs_root: Path | None = None,
        knowledge: Path | None = None,
        cache: Path | None = None,
        dwg2dxf: Path | None = None,
        model: Path | None = None,
    ) -> "ServiceLocation":
        knowledge_root = locate_knowledge_root(knowledge)
        return cls(
            jobs_root=resolve_jobs_root(jobs_root),
            knowledge_root=knowledge_root,
            cache_directory=resolve_cache_directory(cache, knowledge_root),
            converter=locate_dwg2dxf(dwg2dxf, knowledge_root),
            model=locate_model(model, knowledge_root),
        )


def build_job_service(location: ServiceLocation) -> JobService:
    def pipeline_factory(config: RunConfig, use_model: bool) -> PlanningPipeline:
        guidance = model_guidance_of(location) if use_model else rule_guidance
        components = PipelineComponents.assemble(
            location.knowledge_root, config, location.converter, location.cache_directory, guidance
        )
        return PlanningPipeline(components, config)

    return JobService(
        JobRepository(location.jobs_root),
        UploadStorage(),
        pipeline_factory,
        RunConfigLoader(),
        current_timestamp,
    )


def model_guidance_of(location: ServiceLocation) -> GuidanceFactory:
    if location.model is None:
        return rule_guidance
    from greenplan_ml.score_map import model_guidance

    return model_guidance(location.model)


def execute_in_worker(location: ServiceLocation, job_id: str) -> None:
    build_job_service(location).execute(job_id)
