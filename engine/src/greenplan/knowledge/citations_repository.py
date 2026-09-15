from pathlib import Path

from greenplan.domain.errors import KnowledgeValidationError
from greenplan.domain.norms import Citation
from greenplan.knowledge.yaml_loader import load_yaml_mapping, require_key


class CitationsRepository:
    def __init__(self, citations: dict[str, Citation]) -> None:
        self._citations = citations

    @classmethod
    def from_file(cls, path: Path) -> "CitationsRepository":
        entries = require_key(load_yaml_mapping(path), "citations", path)
        citations: dict[str, Citation] = {}
        for entry in entries:
            citation = _citation_from(entry)
            if citation.key in citations:
                raise KnowledgeValidationError(f"duplicate citation key '{citation.key}' in {path}")
            citations[citation.key] = citation
        return cls(citations)

    def get(self, key: str) -> Citation:
        if key not in self._citations:
            raise KnowledgeValidationError(f"unknown citation key '{key}'")
        return self._citations[key]

    def contains(self, key: str) -> bool:
        return key in self._citations

    def all(self) -> tuple[Citation, ...]:
        return tuple(self._citations.values())


def _citation_from(entry: dict) -> Citation:
    return Citation(
        key=entry["key"],
        doc_short=entry.get("doc_short", ""),
        locator=entry.get("locator", ""),
        verification=entry.get("verification", "needs_check"),
        doc_full=entry.get("doc_full", ""),
        quote_ru=(entry.get("quote_ru") or "").strip(),
        url=entry.get("url", ""),
        local_text=entry.get("local_text", ""),
        note=entry.get("note", ""),
    )
