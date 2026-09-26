from dataclasses import dataclass

ROW = "row"
GROUP = "group"
SOLITARY = "solitary"
HEDGE = "hedge"
SHRUB_GROUP = "shrub_group"
ELEMENT_KINDS = (ROW, GROUP, SOLITARY, HEDGE, SHRUB_GROUP)


@dataclass(frozen=True, slots=True)
class CompositionElement:
    element_id: str
    kind: str
    target: str
    size: int
    spacing_m: float
    edge_kind: str = ""
