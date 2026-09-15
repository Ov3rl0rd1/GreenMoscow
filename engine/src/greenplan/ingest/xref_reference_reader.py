from ezdxf.document import Drawing

from greenplan.domain.drawing import XrefReference


class XrefReferenceReader:
    def read(self, document: Drawing) -> tuple[XrefReference, ...]:
        declared_paths = self._declared_xref_paths(document)
        references = [
            XrefReference(insert.dxf.name, declared_paths[insert.dxf.name], insert.matrix44())
            for insert in document.modelspace().query("INSERT")
            if insert.dxf.name in declared_paths
        ]
        return self._without_duplicates(references)

    def _declared_xref_paths(self, document: Drawing) -> dict[str, str]:
        return {
            block.name: block.block.dxf.get("xref_path", "")
            for block in document.blocks
            if block.block_record.is_xref
        }

    def _without_duplicates(self, references: list[XrefReference]) -> tuple[XrefReference, ...]:
        unique: dict[tuple[str, tuple[float, ...]], XrefReference] = {}
        for reference in references:
            key = (reference.block_name, tuple(round(value, 6) for value in reference.transform))
            unique.setdefault(key, reference)
        return tuple(unique.values())
