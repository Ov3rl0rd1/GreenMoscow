import ast
import io
import tokenize
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PYTHON_SOURCE_ROOTS = [
    REPOSITORY_ROOT / "engine" / "src",
    REPOSITORY_ROOT / "engine" / "tests",
    REPOSITORY_ROOT / "ml" / "src",
    REPOSITORY_ROOT / "ml" / "tests",
]


def python_source_files() -> list[Path]:
    return sorted(path for root in PYTHON_SOURCE_ROOTS if root.is_dir() for path in root.rglob("*.py"))


def comment_lines(source: str) -> list[int]:
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    return [token.start[0] for token in tokens if token.type == tokenize.COMMENT]


def docstring_lines(source: str) -> list[int]:
    documented_nodes = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    return [
        node.body[0].lineno
        for node in ast.walk(ast.parse(source))
        if isinstance(node, documented_nodes) and node.body and is_string_expression(node.body[0])
    ]


def is_string_expression(statement: ast.stmt) -> bool:
    return (
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and isinstance(statement.value.value, str)
    )


@pytest.mark.parametrize(
    "path", python_source_files(), ids=lambda path: str(path.relative_to(REPOSITORY_ROOT))
)
def test_python_source_has_no_comments_or_docstrings(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    assert comment_lines(source) == [], f"comments found in {path}"
    assert docstring_lines(source) == [], f"docstrings found in {path}"


def test_comment_detector_finds_comments() -> None:
    assert comment_lines("value = 1  " + chr(35) + " note\n") == [1]


def test_docstring_detector_finds_docstrings() -> None:
    assert docstring_lines('def action():\n    "text"\n    return 1\n') == [2]
