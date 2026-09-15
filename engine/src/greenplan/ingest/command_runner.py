import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

TIMEOUT_RETURN_CODE = -1


@dataclass(frozen=True, slots=True)
class CommandResult:
    return_code: int
    stdout: str
    stderr: str

    @property
    def succeeded(self) -> bool:
        return self.return_code == 0


class CommandRunner(Protocol):
    def run(self, arguments: Sequence[str], timeout_s: int) -> CommandResult: ...


class SubprocessCommandRunner:
    def run(self, arguments: Sequence[str], timeout_s: int) -> CommandResult:
        try:
            completed = subprocess.run(list(arguments), capture_output=True, timeout=timeout_s, check=False)
        except subprocess.TimeoutExpired:
            return CommandResult(TIMEOUT_RETURN_CODE, "", f"timeout after {timeout_s} s")
        return CommandResult(
            completed.returncode,
            completed.stdout.decode("utf-8", errors="replace"),
            completed.stderr.decode("utf-8", errors="replace"),
        )
