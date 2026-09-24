import sys
from pathlib import Path

import pytest

from greenplan.cli.commands import (
    InspectCommand,
    RunCommand,
    VerifyCommand,
    model_guidance,
    placement_guidance,
    with_territory,
)
from greenplan.cli.main import build_parser
from greenplan.domain.errors import ConfigurationError
from greenplan.pipeline.environment import MODEL_VARIABLE, locate_model
from greenplan.pipeline.run_config import RunConfig
from greenplan.placement.guidance import rule_guidance

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


def test_territory_reaches_the_configuration() -> None:
    arguments = run_arguments("--territory", "residential_yard")
    assert with_territory(RunConfig(), arguments.territory).territory.category == "residential_yard"
    assert with_territory(RunConfig(), None).territory.category == ""


def test_without_a_model_the_rules_decide(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(MODEL_VARIABLE, raising=False)
    assert placement_guidance(run_arguments(), tmp_path / "knowledge") is rule_guidance


def test_no_ml_overrides_a_given_model(tmp_path: Path) -> None:
    arguments = run_arguments("--model", "model.onnx", "--no-ml")
    assert placement_guidance(arguments, tmp_path / "knowledge") is rule_guidance


def test_missing_model_file_is_reported(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="model file not found"):
        locate_model(tmp_path / "absent.onnx", tmp_path / "knowledge")


def test_model_path_can_come_from_the_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    model = tmp_path / "guide.onnx"
    model.write_bytes(b"onnx")
    monkeypatch.setenv(MODEL_VARIABLE, str(model))
    assert locate_model(None, tmp_path / "knowledge") == model


def test_missing_ml_package_is_reported_clearly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "greenplan_ml.score_map", None)
    with pytest.raises(ConfigurationError, match="greenplan-ml"):
        model_guidance(MODEL_PATH)
