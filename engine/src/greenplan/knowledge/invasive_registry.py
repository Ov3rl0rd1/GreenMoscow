import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from greenplan.knowledge.plant_catalog import Species
from greenplan.knowledge.yaml_loader import load_yaml_mapping, require_key

ALLOWED = "allowed"
ALLOWED_WITH_CONTROL = "allowed_with_control"
CONDITIONAL = "conditional"
EXCLUDED = "excluded"
STATUS_BY_POLICY = {"exclude": EXCLUDED, "exclude_with_warning": EXCLUDED, "conditional": CONDITIONAL}
CONFLICTING_VERIFICATION = "conflicting"
UNVERIFIED_CONFLICT_POLICY = "unverified_conflict"
FEDERAL_CENTRAL_POLICY = "federal_77_central"
ASSORTMENT_CONFLICT_PREFIX = "conflicting"
GENUS_ONLY_MARKER = "spp."


@dataclass(frozen=True, slots=True)
class InvasiveListing:
    latin_key: str
    status: str
    source_ref: str
    group: str


@dataclass(frozen=True, slots=True)
class InvasiveVerdict:
    status: str
    source_refs: tuple[str, ...] = ()
    groups: tuple[str, ...] = ()


class InvasiveRegistry:
    def __init__(self, listings: Iterable[InvasiveListing], assortment_conflict_source_ref: str) -> None:
        self._listings = tuple(listings)
        self._assortment_conflict_source_ref = assortment_conflict_source_ref

    @classmethod
    def from_file(cls, path: Path) -> "InvasiveRegistry":
        content = load_yaml_mapping(path)
        policy = require_key(content, "meta", path)["generator_policy"]
        moscow = require_key(content, "moscow_369pp", path)
        federal = require_key(content, "federal_mpr_77_2026", path)
        listings = [*_moscow_listings(moscow, policy), *_federal_listings(federal, policy)]
        return cls(listings, moscow["source_ref"])

    def verdict(self, species: Species) -> InvasiveVerdict:
        latin = normalized_latin(species.latin)
        matched = [listing for listing in self._listings if _mentions(latin, listing.latin_key)]
        if species.invasive_status and species.invasive_status.startswith(ASSORTMENT_CONFLICT_PREFIX):
            matched.append(
                InvasiveListing(
                    "", CONDITIONAL, self._assortment_conflict_source_ref, species.invasive_status
                )
            )
        if not matched:
            return InvasiveVerdict(ALLOWED)
        status = EXCLUDED if any(listing.status == EXCLUDED for listing in matched) else CONDITIONAL
        return InvasiveVerdict(
            status,
            tuple(sorted({listing.source_ref for listing in matched})),
            tuple(sorted({listing.group for listing in matched})),
        )


def _moscow_listings(moscow: Mapping[str, Any], policy: Mapping[str, str]) -> list[InvasiveListing]:
    listings: list[InvasiveListing] = []
    for group, data in moscow["groups"].items():
        conflicting = data.get("verification") == CONFLICTING_VERIFICATION
        status = STATUS_BY_POLICY[policy[UNVERIFIED_CONFLICT_POLICY if conflicting else f"group_{group}"]]
        listings.extend(
            InvasiveListing(latin_key(item["latin"]), status, moscow["source_ref"], f"369-ПП:{group}")
            for item in data["species"]
        )
    return listings


def _federal_listings(federal: Mapping[str, Any], policy: Mapping[str, str]) -> list[InvasiveListing]:
    status = STATUS_BY_POLICY[policy[FEDERAL_CENTRAL_POLICY]]
    return [
        InvasiveListing(latin_key(item["latin"]), status, federal["source_ref"], "МПР-77:ЦФО")
        for item in federal["central_federal_district"]
    ]


def normalized_latin(latin: str) -> str:
    return " ".join(latin.lower().replace("×", " ").split())


def latin_key(latin: str) -> str:
    first_name = re.split(r"[/,]", latin)[0]
    tokens = normalized_latin(first_name).split()
    if len(tokens) >= 2 and tokens[1] != GENUS_ONLY_MARKER:
        return f"{tokens[0]} {tokens[1]}"
    return tokens[0] if tokens else ""


def _mentions(latin: str, key: str) -> bool:
    return bool(key) and re.search(rf"\b{re.escape(key)}\b", latin) is not None
