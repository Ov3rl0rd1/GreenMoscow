import argparse
import sys
from collections.abc import Sequence

from greenplan import __version__
from greenplan.cli.commands import (
    EXIT_ERROR,
    Command,
    InspectCommand,
    RunCommand,
    ServeCommand,
    VerifyCommand,
)
from greenplan.domain.errors import GreenPlanError

PROGRAM_NAME = "greenplan"


def build_parser(commands: Sequence[Command]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM_NAME, description="Проектирование озеленения с учётом подземных коммуникаций"
    )
    parser.add_argument("--version", action="version", version=f"{PROGRAM_NAME} {__version__}")
    subparsers = parser.add_subparsers(required=True)
    for command in commands:
        command.register(subparsers)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    commands = (RunCommand(), VerifyCommand(), InspectCommand(), ServeCommand())
    arguments = build_parser(commands).parse_args(argv)
    try:
        return arguments.command.execute(arguments)
    except GreenPlanError as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
