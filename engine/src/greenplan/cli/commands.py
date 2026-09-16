import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Protocol

import uvicorn

from greenplan.domain.errors import ConfigurationError
from greenplan.domain.norms import TREE
from greenplan.pipeline.components import PipelineComponents
from greenplan.pipeline.environment import locate_dwg2dxf, locate_knowledge_root, resolve_cache_directory
from greenplan.pipeline.pipeline_request import PipelineRequest
from greenplan.pipeline.planning_pipeline import PipelineResult, PlanningPipeline
from greenplan.pipeline.run_config import RunConfig, RunConfigLoader
from greenplan.placement.placement_settings import PlacementSettings
from greenplan.placement.score_maps import RuleScoreMap, ScoreMapProvider
from greenplan.verify.verification_model import VerificationReport
from greenplan.verify.verification_writers import write_verification_json, write_verification_markdown

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_VERIFICATION_FAILED = 2
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000


class Command(Protocol):
    name: str

    def register(self, subparsers: argparse._SubParsersAction) -> None: ...

    def execute(self, arguments: argparse.Namespace) -> int: ...


class RunCommand:
    name = "run"

    def register(self, subparsers: argparse._SubParsersAction) -> None:
        parser = subparsers.add_parser(self.name, help="спроектировать посадки для чертежа")
        add_environment_arguments(parser)
        parser.add_argument("--output", required=True, type=Path, help="каталог результатов")
        parser.add_argument("--title", help="название участка в отчётах")
        parser.add_argument("--model", type=Path, help="ONNX-модель подсказок размещения деревьев")
        parser.add_argument("--no-ml", action="store_true", help="игнорировать модель и считать по правилам")
        parser.set_defaults(command=self)

    def execute(self, arguments: argparse.Namespace) -> int:
        pipeline = build_pipeline(arguments)
        request = PipelineRequest(
            arguments.input, arguments.output, arguments.title or arguments.input.stem, arguments.search_root
        )
        result = pipeline.run(request)
        print_run(result)
        return EXIT_OK if result.verification.is_valid else EXIT_VERIFICATION_FAILED


class VerifyCommand:
    name = "verify"

    def register(self, subparsers: argparse._SubParsersAction) -> None:
        parser = subparsers.add_parser(self.name, help="независимо проверить выходной DXF")
        add_environment_arguments(parser)
        parser.add_argument("--dxf", required=True, type=Path, help="выходной DXF с посадками")
        parser.add_argument("--report-dir", type=Path, help="куда записать verification_report.*")
        parser.set_defaults(command=self)

    def execute(self, arguments: argparse.Namespace) -> int:
        pipeline = build_pipeline(arguments)
        report = pipeline.verify_output(
            pipeline.recognize(arguments.input, arguments.search_root), arguments.dxf
        )
        if arguments.report_dir is not None:
            write_verification_json(report, arguments.report_dir)
            write_verification_markdown(report, arguments.report_dir)
        print_verification(report)
        return EXIT_OK if report.is_valid else EXIT_VERIFICATION_FAILED


class InspectCommand:
    name = "inspect"

    def register(self, subparsers: argparse._SubParsersAction) -> None:
        parser = subparsers.add_parser(self.name, help="показать, что распознано на чертеже")
        add_environment_arguments(parser)
        parser.set_defaults(command=self)

    def execute(self, arguments: argparse.Namespace) -> int:
        recognized = build_pipeline(arguments).recognize(arguments.input, arguments.search_root)
        site = recognized.site
        payload = {
            "main": str(recognized.drawing_set.main.path),
            "references": [str(drawing.path) for drawing in recognized.drawing_set.references],
            "unresolved_references": list(recognized.drawing_set.unresolved_references),
            "boundary_area_m2": round(site.boundary.area, 1),
            "plantable_area_m2": round(site.plantable_surface.area, 1),
            "kept_trees": len(site.kept_trees()),
            "diagnostics": asdict(site.diagnostics),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return EXIT_OK


class ServeCommand:
    name = "serve"

    def register(self, subparsers: argparse._SubParsersAction) -> None:
        parser = subparsers.add_parser(self.name, help="запустить HTTP API со Swagger (/docs)")
        parser.add_argument("--host", default=DEFAULT_HOST)
        parser.add_argument("--port", type=int, default=DEFAULT_PORT)
        parser.set_defaults(command=self)

    def execute(self, arguments: argparse.Namespace) -> int:
        uvicorn.run(
            "greenplan.api.app:create_app_from_environment",
            host=arguments.host,
            port=arguments.port,
            factory=True,
        )
        return EXIT_OK


def add_environment_arguments(parser: argparse.ArgumentParser) -> None:
    parser.set_defaults(model=None, no_ml=False)
    parser.add_argument("--input", required=True, type=Path, help="главный DWG/DXF объекта")
    parser.add_argument(
        "--search-root", type=Path, help="где искать внешние ссылки (по умолчанию — папка входа)"
    )
    parser.add_argument("--config", type=Path, help="YAML с переопределением настроек")
    parser.add_argument("--knowledge", type=Path, help="каталог knowledge/")
    parser.add_argument("--cache", type=Path, help="кеш сконвертированных DXF")
    parser.add_argument("--dwg2dxf", type=Path, help="путь к dwg2dxf")


def build_pipeline(arguments: argparse.Namespace) -> PlanningPipeline:
    knowledge_root = locate_knowledge_root(arguments.knowledge)
    config = RunConfigLoader().load(arguments.config)
    components = PipelineComponents.assemble(
        knowledge_root,
        config,
        locate_dwg2dxf(arguments.dwg2dxf, knowledge_root),
        resolve_cache_directory(arguments.cache, knowledge_root),
        tree_score_map(arguments, config),
    )
    return PlanningPipeline(components, config)


def tree_score_map(arguments: argparse.Namespace, config: RunConfig) -> ScoreMapProvider | None:
    if arguments.model is None or arguments.no_ml:
        return None
    return model_score_map(arguments.model, config.placement)


def model_score_map(path: Path, placement: PlacementSettings) -> ScoreMapProvider:
    try:
        from greenplan_ml.score_map import ModelScoreMap
    except ImportError as error:
        raise ConfigurationError(
            "для --model нужен пакет greenplan-ml: установите его или уберите флаг"
        ) from error
    return ModelScoreMap.from_file(path, RuleScoreMap(placement.tree_score), TREE)


def print_run(result: PipelineResult) -> None:
    summary = result.report_summary
    print(
        f"Деревьев: {summary.trees}, кустарников: {summary.shrubs}, "
        f"условно: {summary.conditional}, отказов: {summary.rejected}"
    )
    print_verification(result.verification)
    print(f"DXF: {result.output_dxf}")
    for stage, seconds in result.timings_s.items():
        print(f"  {stage}: {seconds} с")


def print_verification(report: VerificationReport) -> None:
    verdict = "пройдена" if report.is_valid else "НЕ пройдена"
    integrity = "цел" if report.integrity.is_intact else "ИЗМЕНЁН"
    print(f"Проверка: {verdict}; нарушений: {len(report.violations)}; исходник: {integrity}")
