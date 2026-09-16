from pathlib import Path
from typing import Annotated, Any

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from greenplan import __version__
from greenplan.api.job_repository import JobRepository
from greenplan.api.job_service import JobService, UploadedFile
from greenplan.api.norms_view import norms_payload
from greenplan.api.schemas import HealthResponse, JobResponse
from greenplan.api.upload_storage import UploadStorage
from greenplan.domain.errors import (
    ConfigurationError,
    InvalidUploadError,
    JobNotFoundError,
    KnowledgeValidationError,
)
from greenplan.knowledge.norms_repository import NormsRepository
from greenplan.pipeline.components import PipelineComponents
from greenplan.pipeline.environment import (
    current_timestamp,
    locate_dwg2dxf,
    locate_knowledge_root,
    resolve_cache_directory,
    resolve_jobs_root,
)
from greenplan.pipeline.planning_pipeline import PlanningPipeline
from greenplan.pipeline.run_config import RunConfig, RunConfigLoader

API_PREFIX = "/api/v1"
API_TITLE = "GreenPlan API"
API_DESCRIPTION = (
    "Автоматическое проектирование озеленения с учётом подземных коммуникаций: загрузка чертежа, "
    "расчёт посадок на отдельных слоях DXF, объяснения со ссылками на нормы, независимая проверка."
)
DEFAULT_TITLE = "Участок"
HEALTHY = "ok"
HTTP_ACCEPTED = 202
HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
REQUEST_ERRORS = (InvalidUploadError, ConfigurationError, KnowledgeValidationError)


def create_app(service: JobService, knowledge_root: Path, dwg2dxf_available: bool) -> FastAPI:
    app = FastAPI(title=API_TITLE, version=__version__, description=API_DESCRIPTION)
    norms = norms_payload(NormsRepository.from_knowledge(knowledge_root))

    @app.get("/healthz", response_model=HealthResponse, tags=["service"])
    def health() -> HealthResponse:
        return HealthResponse(status=HEALTHY, version=__version__, dwg2dxf_available=dwg2dxf_available)

    @app.get(f"{API_PREFIX}/norms", tags=["norms"])
    def get_norms() -> dict[str, Any]:
        return norms

    @app.post(f"{API_PREFIX}/jobs", response_model=JobResponse, status_code=HTTP_ACCEPTED, tags=["jobs"])
    async def create_job(
        background_tasks: BackgroundTasks,
        drawing: Annotated[
            list[UploadFile],
            File(description="один или несколько .dxf/.dwg (генплан, подоснова) либо .zip папки объекта"),
        ],
        title: Annotated[str, Form()] = DEFAULT_TITLE,
        main_file: Annotated[
            str | None, Form(description="главный чертёж; без него выбирается по имени и размеру")
        ] = None,
        config: Annotated[UploadFile | None, File(description="YAML с настройками прогона")] = None,
    ) -> JobResponse:
        uploads = [UploadedFile(item.filename or "", await item.read()) for item in drawing]
        config_text = (await config.read()).decode("utf-8") if config is not None else None
        try:
            record = service.create(uploads, title, main_file, config_text)
        except REQUEST_ERRORS as error:
            raise HTTPException(status_code=HTTP_BAD_REQUEST, detail=str(error)) from error
        background_tasks.add_task(service.execute, record.job_id)
        return JobResponse.from_record(record)

    @app.get(f"{API_PREFIX}/jobs", response_model=list[JobResponse], tags=["jobs"])
    def list_jobs() -> list[JobResponse]:
        return [JobResponse.from_record(record) for record in service.all()]

    @app.get(f"{API_PREFIX}/jobs/{{job_id}}", response_model=JobResponse, tags=["jobs"])
    def get_job(job_id: str) -> JobResponse:
        try:
            return JobResponse.from_record(service.get(job_id))
        except JobNotFoundError as error:
            raise HTTPException(status_code=HTTP_NOT_FOUND, detail=str(error)) from error

    @app.get(f"{API_PREFIX}/jobs/{{job_id}}/artifacts/{{name}}", tags=["jobs"])
    def get_artifact(job_id: str, name: str) -> FileResponse:
        try:
            path = service.artifact(job_id, name)
        except JobNotFoundError as error:
            raise HTTPException(status_code=HTTP_NOT_FOUND, detail=str(error)) from error
        return FileResponse(path, filename=name)

    return app


def create_app_from_environment(
    jobs_root: Path | None = None,
    knowledge: Path | None = None,
    cache: Path | None = None,
    dwg2dxf: Path | None = None,
) -> FastAPI:
    knowledge_root = locate_knowledge_root(knowledge)
    converter = locate_dwg2dxf(dwg2dxf, knowledge_root)
    cache_directory = resolve_cache_directory(cache, knowledge_root)

    def pipeline_factory(config: RunConfig) -> PlanningPipeline:
        return PlanningPipeline(
            PipelineComponents.assemble(knowledge_root, config, converter, cache_directory), config
        )

    service = JobService(
        JobRepository(resolve_jobs_root(jobs_root)),
        UploadStorage(),
        pipeline_factory,
        RunConfigLoader(),
        current_timestamp,
    )
    return create_app(service, knowledge_root, converter is not None)
