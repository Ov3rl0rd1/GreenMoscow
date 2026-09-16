from pathlib import Path

from greenplan_ml.cli.commands import (
    DEFAULT_OBJECTS_FILE,
    BuildDatasetCommand,
    EvaluateCommand,
    ExportCommand,
    TrainCommand,
)
from greenplan_ml.cli.main import build_parser
from greenplan_ml.sample_builder import SampleSettings

COMMANDS = (BuildDatasetCommand(), TrainCommand(), ExportCommand(), EvaluateCommand())


def parse(*argv: str):
    return build_parser(COMMANDS).parse_args(argv)


def build_arguments(*extra: str):
    return parse("build-dataset", "--dataset-root", "pilot", "--output", "out", *extra)


def test_window_defaults_are_numbers_not_dataclass_slots() -> None:
    arguments = build_arguments()
    defaults = SampleSettings()
    assert arguments.crop_size == defaults.crop_size
    assert arguments.stride == defaults.stride
    assert isinstance(arguments.crop_size, int)
    assert isinstance(arguments.stride, int)


def test_window_can_be_overridden() -> None:
    arguments = build_arguments("--crop-size", "128", "--stride", "96")
    assert (arguments.crop_size, arguments.stride) == (128, 96)


def test_objects_file_and_filters_have_usable_defaults() -> None:
    arguments = build_arguments()
    assert arguments.objects == DEFAULT_OBJECTS_FILE
    assert arguments.levels is None
    assert arguments.only is None


def test_object_filter_collects_every_identifier() -> None:
    arguments = build_arguments("--only", "bagritskogo", "berzarina", "--levels", "A")
    assert arguments.only == ["bagritskogo", "berzarina"]
    assert arguments.levels == ["A"]


def test_training_overrides_are_absent_until_asked() -> None:
    arguments = parse("train", "--dataset", "data", "--output", "run")
    assert arguments.epochs is None
    assert arguments.batch_size is None
    assert arguments.profile == "rtx3050"
    assert arguments.seed == 0


def test_training_overrides_reach_the_namespace() -> None:
    arguments = parse("train", "--dataset", "d", "--output", "r", "--epochs", "3", "--batch-size", "2")
    assert (arguments.epochs, arguments.batch_size) == (3, 2)


def test_evaluation_tolerances_default_to_two_and_three_metres() -> None:
    arguments = parse("evaluate", "--dataset", "d", "--model", "m.onnx", "--output", "o")
    assert tuple(arguments.tolerances) == (2.0, 3.0)
    assert arguments.objects is None


def test_export_takes_a_checkpoint_and_a_target_path() -> None:
    arguments = parse("export", "--checkpoint", "run/model.pt", "--output", "model.onnx")
    assert arguments.checkpoint == Path("run/model.pt")
    assert arguments.output == Path("model.onnx")
    assert isinstance(arguments.sample_size, int)
