from dataclasses import dataclass, field
from pathlib import Path

from ezdxf.math import Matrix44

from greenplan.domain.drawing import DrawingSet, LoadedDrawing, XrefReference
from greenplan.domain.errors import GreenPlanError
from greenplan.ingest.drawing_file_opener import DrawingFileOpener
from greenplan.ingest.xref_file_locator import XrefFileLocator
from greenplan.ingest.xref_reference_reader import XrefReferenceReader

DEFAULT_MAX_XREF_DEPTH = 2


@dataclass
class _TraversalState:
    loaded: list[LoadedDrawing] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    visited_paths: set[Path] = field(default_factory=set)


class DrawingSetBuilder:
    def __init__(
        self,
        opener: DrawingFileOpener,
        reference_reader: XrefReferenceReader,
        max_xref_depth: int = DEFAULT_MAX_XREF_DEPTH,
    ) -> None:
        self._opener = opener
        self._reference_reader = reference_reader
        self._max_xref_depth = max_xref_depth

    def build(self, main_path: Path, search_root: Path | None = None) -> DrawingSet:
        locator = XrefFileLocator(search_root or main_path.parent)
        main = LoadedDrawing(main_path.stem, main_path, self._opener.open(main_path), Matrix44(), True)
        state = _TraversalState(visited_paths={main_path.resolve()})
        self._load_references_of(main, locator, state, depth=1)
        return DrawingSet(main, tuple(state.loaded), tuple(state.unresolved))

    def _load_references_of(
        self, parent: LoadedDrawing, locator: XrefFileLocator, state: _TraversalState, depth: int
    ) -> None:
        if depth > self._max_xref_depth:
            return
        for reference in self._reference_reader.read(parent.document):
            child = self._load_reference(reference, parent, locator, state)
            if child is not None:
                self._load_references_of(child, locator, state, depth + 1)

    def _load_reference(
        self,
        reference: XrefReference,
        parent: LoadedDrawing,
        locator: XrefFileLocator,
        state: _TraversalState,
    ) -> LoadedDrawing | None:
        located = locator.locate(reference.declared_path, parent.path.parent)
        if located is None:
            state.unresolved.append(reference.declared_path)
            return None
        if located.resolve() in state.visited_paths:
            return None
        state.visited_paths.add(located.resolve())
        return self._open_reference(reference, located, parent, state)

    def _open_reference(
        self, reference: XrefReference, located: Path, parent: LoadedDrawing, state: _TraversalState
    ) -> LoadedDrawing | None:
        try:
            document = self._opener.open(located)
        except GreenPlanError:
            state.unresolved.append(reference.declared_path)
            return None
        transform = Matrix44.chain(reference.transform, parent.transform)
        child = LoadedDrawing(reference.block_name, located, document, transform, False)
        state.loaded.append(child)
        return child
