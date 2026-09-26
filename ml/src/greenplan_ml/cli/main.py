import argparse
import sys
from collections.abc import Sequence

from greenplan.domain.errors import GreenPlanError
from greenplan_ml import __version__
from greenplan_ml.cli.commands import (
    EXIT_ERROR,
    AuditReferenceCommand,
    BuildDatasetCommand,
    CalibrateCommand,
    Command,
    EvaluateCommand,
    ExportCommand,
    FiguresCommand,
    SimilarityCommand,
    TrainCommand,
)

PROGRAM_NAME = "greenplan-ml"


def build_parser(commands: Sequence[Command]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM_NAME, description="Обучение и оценка модели предложений по размещению посадок"
    )
    parser.add_argument("--version", action="version", version=f"{PROGRAM_NAME} {__version__}")
    subparsers = parser.add_subparsers(required=True)
    for command in commands:
        command.register(subparsers)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    commands = (
        BuildDatasetCommand(),
        TrainCommand(),
        ExportCommand(),
        CalibrateCommand(),
        EvaluateCommand(),
        AuditReferenceCommand(),
        SimilarityCommand(),
        FiguresCommand(),
    )
    arguments = build_parser(commands).parse_args(argv)
    try:
        return arguments.command.execute(arguments)
    except GreenPlanError as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
