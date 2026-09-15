from pathlib import Path
from typing import Any

import yaml

from greenplan.domain.errors import KnowledgeValidationError


def load_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise KnowledgeValidationError(f"knowledge file not found: {path}")
    try:
        content = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise KnowledgeValidationError(f"invalid YAML in {path}: {error}") from error
    if not isinstance(content, dict):
        raise KnowledgeValidationError(f"knowledge file must contain a mapping: {path}")
    return content


def require_key(mapping: dict[str, Any], key: str, source: Path) -> Any:
    if key not in mapping:
        raise KnowledgeValidationError(f"missing key '{key}' in {source}")
    return mapping[key]
