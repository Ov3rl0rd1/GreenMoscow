from pathlib import Path
from typing import Annotated, Any

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from greenplan import __version__
from greenplan.api.job_runner import InProcessJobRunner, IsolatedJobRunner, JobRunner
from greenplan.api.job_service import JobService, UploadedFile
from greenplan.api.norms_view import norms_payload
from greenplan.api.schemas import HealthResponse, JobResponse
from greenplan.api.service_factory import ServiceLocation, build_job_service
from greenplan.api.upload_names import upload_file_name
from greenplan.domain.errors import (
    ConfigurationError,
    InvalidUploadError,
    JobNotFoundError,
    KnowledgeValidationError,
)
from greenplan.knowledge.norms_repository import NormsRepository
from greenplan.knowledge.territory_catalog import TerritoryCatalog

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


def create_app(
    service: JobService, runner: JobRunner, knowledge_root: Path, dwg2dxf_available: bool
) -> FastAPI:
    app = FastAPI(title=API_TITLE, version=__version__, description=API_DESCRIPTION)
    norms = norms_payload(NormsRepository.from_knowledge(knowledge_root))
    territories = TerritoryCatalog.from_knowledge(knowledge_root)

    @app.get("/healthz", response_model=HealthResponse, tags=["service"])
    def health() -> HealthResponse:
        return HealthResponse(status=HEALTHY, version=__version__, dwg2dxf_available=dwg2dxf_available)

    @app.get(f"{API_PREFIX}/norms", tags=["norms"])
    def get_norms() -> dict[str, Any]:
        return norms

    @app.get(f"{API_PREFIX}/territories", tags=["norms"])
    def get_territories() -> list[dict[str, str]]:
        return [
            {"id": item.category_id, "name_ru": item.name_ru, "composition_ru": item.composition_ru}
            for item in territories.categories()
        ]

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
        territory: Annotated[
            str | None, Form(description="категория территории: /api/v1/territories")
        ] = None,
    ) -> JobResponse:
        uploads = [UploadedFile(upload_file_name(item.filename or ""), await item.read()) for item in drawing]
        config_text = (await config.read()).decode("utf-8") if config is not None else None
        try:
            record = service.create(uploads, title, main_file, config_text, territory)
        except REQUEST_ERRORS as error:
            raise HTTPException(status_code=HTTP_BAD_REQUEST, detail=str(error)) from error
        background_tasks.add_task(runner.run, record.job_id)
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
    isolated: bool = True,
) -> FastAPI:
    location = ServiceLocation.resolve(jobs_root, knowledge, cache, dwg2dxf)
    service = build_job_service(location)
    service.fail_interrupted()
    runner: JobRunner = IsolatedJobRunner(service, location) if isolated else InProcessJobRunner(service)
    return create_app(service, runner, location.knowledge_root, location.converter is not None)
