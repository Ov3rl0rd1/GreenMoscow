from collections.abc import Iterable

from greenplan.explain.explanation_model import CitationView
from greenplan.knowledge.citations_repository import CitationsRepository


class CitationPolicy:
    def __init__(self, repository: CitationsRepository) -> None:
        self._repository = repository

    def view(self, key: str) -> CitationView:
        citation = self._repository.get(key)
        locator = citation.locator if citation.is_verified else None
        text = f"{citation.doc_short}, {locator}" if locator else citation.doc_short
        return CitationView(citation.key, citation.doc_short, locator, citation.verification, text)

    def views(self, keys: Iterable[str]) -> tuple[CitationView, ...]:
        return tuple(self.view(key) for key in dict.fromkeys(keys))
