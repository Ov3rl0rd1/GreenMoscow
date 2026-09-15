from ezdxf.document import Drawing

from greenplan.export.entity_fingerprint import EntityFingerprinter
from greenplan.verify.verification_model import IntegrityReport

LayerSignature = tuple[int, str, bool, bool, bool]


class SourceIntegrityChecker:
    def __init__(self, fingerprinter: EntityFingerprinter) -> None:
        self._fingerprinter = fingerprinter

    def check(self, source: Drawing, output: Drawing) -> IntegrityReport:
        difference = self._fingerprinter.compare(
            self._fingerprinter.modelspace_fingerprints(source),
            self._fingerprinter.modelspace_fingerprints(output),
        )
        source_layers = _layer_signatures(source)
        output_layers = _layer_signatures(output)
        return IntegrityReport(
            missing_handles=difference.missing_handles,
            changed_handles=difference.changed_handles,
            changed_layers=tuple(
                sorted(
                    name for name, signature in source_layers.items() if output_layers.get(name) != signature
                )
            ),
            missing_blocks=tuple(sorted(_block_names(source) - _block_names(output))),
        )


def _layer_signatures(document: Drawing) -> dict[str, LayerSignature]:
    return {
        layer.dxf.name: (layer.color, layer.dxf.linetype, layer.is_on(), layer.is_frozen(), layer.is_locked())
        for layer in document.layers
    }


def _block_names(document: Drawing) -> set[str]:
    return {block.name for block in document.blocks}
