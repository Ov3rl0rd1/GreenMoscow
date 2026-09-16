import sys
from pathlib import Path

import pytest

from greenplan.cli.commands import InspectCommand, RunCommand, VerifyCommand, model_score_map, tree_score_map
from greenplan.cli.main import build_parser
from greenplan.domain.errors import ConfigurationError
from greenplan.pipeline.run_config import RunConfig
from greenplan.placement.placement_settings import PlacementSettings

MODEL_PATH = Path("model.onnx")


def parse(*argv: str):
    return build_parser((RunCommand(), VerifyCommand(), InspectCommand())).parse_args(argv)


def run_arguments(*extra: str):
    return parse("run", "--input", "site.dxf", "--output", "out", *extra)


def test_run_accepts_a_model_path() -> None:
    arguments = run_arguments("--model", "model.onnx")
    assert arguments.model == MODEL_PATH
    assert arguments.no_ml is False


def test_commands_without_the_flag_still_carry_the_defaults() -> None:
    inspected = parse("inspect", "--input", "site.dxf")
    verified = parse("verify", "--input", "site.dxf", "--dxf", "plan.dxf")
    for arguments in (inspected, verified):
        assert arguments.model is None
        assert arguments.no_ml is False


def test_without_a_model_the_rules_decide() -> None:
    assert tree_score_map(run_arguments(), RunConfig()) is None


def test_no_ml_overrides_a_given_model() -> None:
    arguments = run_arguments("--model", "model.onnx", "--no-ml")
    assert tree_score_map(arguments, RunConfig()) is None


def test_missing_ml_package_is_reported_clearly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "greenplan_ml.score_map", None)
    with pytest.raises(ConfigurationError, match="greenplan-ml"):
        model_score_map(MODEL_PATH, PlacementSettings())
