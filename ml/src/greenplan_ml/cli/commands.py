import argparse
from pathlib import Path
from typing import Protocol

import numpy as np

from greenplan.domain.norms import SHRUB, TREE
from greenplan.knowledge.pilot_objects import PilotCatalog
from greenplan.pipeline.environment import locate_dwg2dxf, locate_knowledge_root, resolve_cache_directory
from greenplan.placement.placement_settings import PlacementSettings
from greenplan.placement.score_maps import RuleScoreMap
from greenplan_ml.dataset_builder import DatasetBuilder
from greenplan_ml.evaluation import EvaluationSettings, ModelEvaluator
from greenplan_ml.inference import OnnxHeatmapModel
from greenplan_ml.sample_builder import SampleSettings
from greenplan_ml.sample_store import stored_objects

EXIT_OK = 0
EXIT_ERROR = 1
DEFAULT_OBJECTS_FILE = Path("knowledge/dataset/pilot_objects.yaml")
DEFAULT_SAMPLES = SampleSettings()


class Command(Protocol):
    name: str

    def register(self, subparsers: argparse._SubParsersAction) -> None: ...

    def execute(self, arguments: argparse.Namespace) -> int: ...


class BuildDatasetCommand:
    name = "build-dataset"

    def register(self, subparsers: argparse._SubParsersAction) -> None:
        parser = subparsers.add_parser(self.name, help="собрать обучающие примеры из пилотных объектов")
        parser.add_argument("--dataset-root", required=True, type=Path, help="каталог с объектами датасета")
        parser.add_argument("--output", required=True, type=Path, help="куда сложить примеры")
        parser.add_argument("--objects", type=Path, default=DEFAULT_OBJECTS_FILE, help="YAML со списком пар")
        parser.add_argument("--levels", nargs="*", help="уровни объектов, например A")
        parser.add_argument("--only", nargs="*", help="id объектов, по умолчанию все выбранные")
        parser.add_argument("--crop-size", type=int, default=DEFAULT_SAMPLES.crop_size)
        parser.add_argument("--stride", type=int, default=DEFAULT_SAMPLES.stride)
        add_environment_arguments(parser)
        parser.set_defaults(command=self)

    def execute(self, arguments: argparse.Namespace) -> int:
        knowledge_root = locate_knowledge_root(arguments.knowledge)
        builder = DatasetBuilder.from_knowledge(
            knowledge_root,
            locate_dwg2dxf(arguments.dwg2dxf, knowledge_root),
            resolve_cache_directory(arguments.cache, knowledge_root),
            samples=SampleSettings(crop_size=arguments.crop_size, stride=arguments.stride),
        )
        catalog = PilotCatalog.from_file(arguments.objects)
        reports = builder.build_all(
            catalog, arguments.dataset_root, arguments.output, arguments.levels, arguments.only
        )
        for report in reports:
            status = f"{report.crops} окон, деревьев {report.trees}" if report.is_built else report.reason
            print(f"{report.object_id}: {status}")
        return EXIT_OK if any(report.is_built for report in reports) else EXIT_ERROR


class AuditReferenceCommand:
    name = "audit-reference"

    def register(self, subparsers: argparse._SubParsersAction) -> None:
        parser = subparsers.add_parser(
            self.name, help="проверить эталонные проекты датасета нормативным контролем"
        )
        parser.add_argument("--dataset-root", required=True, type=Path, help="каталог с объектами датасета")
        parser.add_argument("--output", required=True, type=Path, help="куда записать отчёт аудита")
        parser.add_argument("--objects", type=Path, default=DEFAULT_OBJECTS_FILE, help="YAML со списком пар")
        parser.add_argument("--levels", nargs="*", help="уровни объектов, например A")
        parser.add_argument("--only", nargs="*", help="id объектов")
        add_environment_arguments(parser)
        parser.set_defaults(command=self)

    def execute(self, arguments: argparse.Namespace) -> int:
        from greenplan_ml.reference_audit import ReferenceAuditor, write_audit_report

        knowledge_root = locate_knowledge_root(arguments.knowledge)
        auditor = ReferenceAuditor.from_knowledge(
            knowledge_root,
            locate_dwg2dxf(arguments.dwg2dxf, knowledge_root),
            resolve_cache_directory(arguments.cache, knowledge_root),
        )
        catalog = PilotCatalog.from_file(arguments.objects)
        audits = auditor.audit_all(catalog, arguments.dataset_root, arguments.levels, arguments.only)
        for item in audits:
            state = (
                f"посадок {item.plantings}, с нарушением {item.violating_plants} "
                f"({item.violation_share:.0%})"
                if item.checked
                else item.reason
            )
            print(f"{item.object_id}: {state}")
        json_path, markdown_path = write_audit_report(arguments.output, audits)
        print(f"Отчёт: {json_path}, {markdown_path}")
        return EXIT_OK if any(item.checked for item in audits) else EXIT_ERROR


class TrainCommand:
    name = "train"

    def register(self, subparsers: argparse._SubParsersAction) -> None:
        parser = subparsers.add_parser(self.name, help="обучить модель тепловых карт")
        parser.add_argument("--dataset", required=True, type=Path, help="каталог собранных примеров")
        parser.add_argument("--output", required=True, type=Path, help="куда сохранить веса и историю")
        parser.add_argument("--profile", default="rtx3050", help="smoke, rtx3050 или gpu_large")
        parser.add_argument("--validation", nargs="*", default=(), help="id объектов для валидации")
        parser.add_argument("--epochs", type=int, help="переопределить число эпох профиля")
        parser.add_argument("--batch-size", type=int, help="переопределить размер пакета профиля")
        parser.add_argument("--device", help="cuda, cpu")
        parser.add_argument("--seed", type=int, default=0)
        parser.set_defaults(command=self)

    def execute(self, arguments: argparse.Namespace) -> int:
        from dataclasses import replace

        from greenplan_ml.model import HeatmapUNet
        from greenplan_ml.training import (
            PROFILES,
            CropDataset,
            Trainer,
            data_loader,
            seed_everything,
            select_device,
            split_objects,
        )

        objects = stored_objects(arguments.dataset)
        if not objects:
            print("нет собранных примеров")
            return EXIT_ERROR
        profile = PROFILES[arguments.profile]
        if arguments.epochs is not None:
            profile = replace(profile, epochs=arguments.epochs)
        if arguments.batch_size is not None:
            profile = replace(profile, batch_size=arguments.batch_size)
        crop_size = objects[0].meta.crop_size
        if crop_size != profile.crop_size:
            print(f"Внимание: окна датасета {crop_size} px, профиль рассчитан на {profile.crop_size} px")
        seed_everything(arguments.seed)
        train, validation = split_objects(objects, arguments.validation)
        if len(objects) == 1:
            print("Внимание: один объект — он же используется для контроля, метрика валидации завышена")
        device = select_device(arguments.device)
        trainer = Trainer(HeatmapUNet(profile.unet_settings()), profile, device)
        history = trainer.fit(
            data_loader(CropDataset(train, augment=True, seed=arguments.seed), profile, True),
            data_loader(CropDataset(validation), profile, False),
            arguments.output,
            objects[0].meta.grid.cell_size_m,
        )
        print(f"Лучшая эпоха: {history.best_epoch}, веса: {history.checkpoint}")
        return EXIT_OK


class ExportCommand:
    name = "export"

    def register(self, subparsers: argparse._SubParsersAction) -> None:
        parser = subparsers.add_parser(self.name, help="выгрузить обученную модель в ONNX")
        parser.add_argument("--checkpoint", required=True, type=Path, help="model.pt после обучения")
        parser.add_argument("--output", required=True, type=Path, help="путь к .onnx")
        parser.add_argument("--sample-size", type=int, default=128)
        parser.set_defaults(command=self)

    def execute(self, arguments: argparse.Namespace) -> int:
        from greenplan_ml.onnx_export import export_onnx, load_checkpoint, parity_error

        checkpoint = load_checkpoint(arguments.checkpoint)
        path = export_onnx(checkpoint, arguments.output, arguments.sample_size)
        settings = checkpoint.model.settings
        size = max(arguments.sample_size, settings.size_multiple)
        sample = np.zeros((settings.input_channels, size, size), dtype=np.float32)
        print(f"ONNX: {path}; расхождение с PyTorch: {parity_error(checkpoint, path, sample):.2e}")
        return EXIT_OK


class EvaluateCommand:
    name = "evaluate"

    def register(self, subparsers: argparse._SubParsersAction) -> None:
        parser = subparsers.add_parser(self.name, help="сравнить модель с правилами на собранных объектах")
        parser.add_argument("--dataset", required=True, type=Path, help="каталог собранных примеров")
        parser.add_argument("--model", required=True, type=Path, help="модель .onnx")
        parser.add_argument("--output", required=True, type=Path, help="куда записать отчёт")
        parser.add_argument("--objects", nargs="*", help="id объектов, по умолчанию все")
        parser.add_argument("--tolerances", nargs="*", type=float, default=(2.0, 3.0))
        parser.set_defaults(command=self)

    def execute(self, arguments: argparse.Namespace) -> int:
        objects = stored_objects(arguments.dataset, arguments.objects)
        if not objects:
            print("нет собранных примеров")
            return EXIT_ERROR
        placement = PlacementSettings()
        evaluator = ModelEvaluator(
            OnnxHeatmapModel.load(arguments.model),
            {TREE: RuleScoreMap(placement.tree_score), SHRUB: RuleScoreMap(placement.shrub_score)},
            EvaluationSettings(tolerances_m=tuple(arguments.tolerances)),
        )
        report = evaluator.evaluate(objects)
        json_path, markdown_path = report.write(arguments.output)
        for item in report.totals:
            print(
                f"{item.source} {item.target} @{item.tolerance_m:g} м: "
                f"точность {item.precision:.3f}, полнота {item.recall:.3f}, F1 {item.f1:.3f}"
            )
        print(f"Отчёт: {json_path}, {markdown_path}")
        return EXIT_OK


def add_environment_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--knowledge", type=Path, help="каталог knowledge/")
    parser.add_argument("--cache", type=Path, help="кеш сконвертированных DXF")
    parser.add_argument("--dwg2dxf", type=Path, help="путь к dwg2dxf")
