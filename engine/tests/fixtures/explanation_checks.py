import re
from dataclasses import asdict, is_dataclass
from typing import Any

from greenplan.domain.norms import VERIFIED_STATUSES
from greenplan.explain.number_format import format_number

NUMBER_PATTERN = re.compile(r"\d+(?:[.,]\d+)*")
EXPLANATION_TEXT_FIELD = "explanation_ru"


def numbers_in_text(text: str) -> set[str]:
    return {token.replace(".", ",") for token in NUMBER_PATTERN.findall(text)}


def numbers_in_structure(value: Any) -> set[str]:
    if is_dataclass(value):
        return numbers_in_structure(asdict(value))
    if isinstance(value, bool) or value is None:
        return set()
    if isinstance(value, int | float):
        return {format_number(abs(value)), str(abs(value))}
    if isinstance(value, str):
        return numbers_in_text(value)
    if isinstance(value, dict):
        return set().union(
            set(),
            *(numbers_in_structure(item) for key, item in value.items() if key != EXPLANATION_TEXT_FIELD),
        )
    if isinstance(value, list | tuple):
        return set().union(set(), *(numbers_in_structure(item) for item in value))
    return set()


def unexplained_numbers(explanation: Any) -> set[str]:
    return numbers_in_text(explanation.explanation_ru) - numbers_in_structure(explanation)


def citations_violating_policy(value: Any) -> list[dict]:
    if is_dataclass(value):
        return citations_violating_policy(asdict(value))
    if isinstance(value, dict):
        own = [value] if _is_unverified_citation_with_locator(value) else []
        return own + [found for item in value.values() for found in citations_violating_policy(item)]
    if isinstance(value, list | tuple):
        return [found for item in value for found in citations_violating_policy(item)]
    return []


def _is_unverified_citation_with_locator(value: dict) -> bool:
    return (
        "verification" in value
        and "locator" in value
        and value["verification"] not in VERIFIED_STATUSES
        and value["locator"] is not None
    )
