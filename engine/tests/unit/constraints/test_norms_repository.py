from pathlib import Path

import pytest

from greenplan.domain.errors import KnowledgeValidationError
from greenplan.domain.norms import PROHIBITIVE, SHRUB, TREE, ZONE_RULE
from greenplan.knowledge.citations_repository import CitationsRepository
from greenplan.knowledge.norms_repository import NormsRepository


@pytest.fixture(scope="module")
def repository(knowledge_root: Path) -> NormsRepository:
    return NormsRepository.from_knowledge(knowledge_root)


def test_all_rules_are_loaded_with_resolvable_citations(repository: NormsRepository) -> None:
    rules = repository.rules()
    assert len(rules) > 40
    for rule in rules:
        for key in rule.source_refs:
            assert repository.citations.contains(key), (rule.rule_id, key)


def test_gas_table_rule_has_tree_distance_and_unregulated_shrub(repository: NormsRepository) -> None:
    tree_rule = repository.rule("sp42_gas_tree")
    shrub_rule = repository.rule("sp42_gas_shrub")
    assert tree_rule.severity == PROHIBITIVE
    assert tree_rule.distance_for(TREE) == pytest.approx(1.5)
    assert shrub_rule.distance_for(SHRUB) is None


def test_protection_zone_rule_is_parsed_as_zone(repository: NormsRepository) -> None:
    rule = repository.rule("pp878_zone")
    assert rule.rule_type == ZONE_RULE
    assert rule.zone_m == pytest.approx(2.0)
    assert set(rule.targets) == {TREE, SHRUB}


def test_per_target_distance_mapping_is_parsed(repository: NormsRepository) -> None:
    rule = repository.rule("utility_tunnel_tree_assumed")
    assert rule.distance_for(TREE) == pytest.approx(2.0)
    assert rule.distance_for(SHRUB) == pytest.approx(1.0)
    assert rule.is_assumption


def test_verified_citation_reports_verified(repository: NormsRepository) -> None:
    assert repository.citations.get("sp42_t9_1_gas_sewer").is_verified
    assert not repository.citations.get("pue").is_verified


def test_defaults_are_read_from_meta(repository: NormsRepository) -> None:
    assert repository.defaults.crown_base_diameter_m == pytest.approx(5.0)
    assert repository.defaults.trunk_diameter_at_planting_m == pytest.approx(0.10)


def test_unknown_citation_reference_is_rejected(tmp_path: Path, knowledge_root: Path) -> None:
    norms = tmp_path / "norms.yaml"
    norms.write_text(
        "meta:\n  crown_rule: {base_crown_diameter_m: 5.0, source_ref: sp42_t9_1_note1}\n"
        "  defaults: {unknown_pipe_outer_diameter_m: 0.5, unknown_heating_channel_width_m: 1.5,"
        " trunk_diameter_at_planting_m: 0.1}\n"
        "rules:\n  - {id: bad, obstacle: gas_pipeline, target: tree, distance_m: 1.0,"
        " severity: prohibitive, source_ref: missing_key}\n",
        encoding="utf-8",
    )
    citations = CitationsRepository.from_file(knowledge_root / "rules" / "citations.yaml")
    with pytest.raises(KnowledgeValidationError):
        NormsRepository.from_files(norms, citations)
