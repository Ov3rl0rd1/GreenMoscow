from pathlib import Path

import pytest

from greenplan.domain.errors import ConfigurationError
from greenplan.pipeline.environment import KNOWLEDGE_ROOT_VARIABLE, locate_knowledge_root
from greenplan.pipeline.run_config import RunConfig, RunConfigLoader, merged_config_text

LOADER = RunConfigLoader()


def write_config(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_missing_config_gives_defaults() -> None:
    assert LOADER.load(None) == RunConfig()


def test_nested_overrides_are_applied_with_numeric_coercion(tmp_path: Path) -> None:
    config = LOADER.load(
        write_config(
            tmp_path,
            "placement:\n  cell_size_m: 1\n  tree_score:\n    preferred_edge_distance_m: 4\n"
            "species:\n  allow_conditional_species: true\nexport:\n  layer_prefix: GP\n",
        )
    )
    assert config.placement.cell_size_m == 1.0
    assert isinstance(config.placement.cell_size_m, float)
    assert config.placement.tree_score.preferred_edge_distance_m == 4.0
    assert config.placement.tree_score.edge_tolerance_m == RunConfig().placement.tree_score.edge_tolerance_m
    assert config.species.allow_conditional_species is True
    assert config.export.layer_prefix == "GP"


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("placement:\n  cell_size: 1\n", "config.placement.cell_size"),
        ("unknown_section:\n  a: 1\n", "config.unknown_section"),
        ("placement:\n  cell_size_m: fast\n", "config.placement.cell_size_m"),
        ("species:\n  allow_conditional_species: 1\n", "config.species.allow_conditional_species"),
        ("placement: 5\n", "config.placement"),
    ],
)
def test_invalid_settings_are_rejected_with_their_path(tmp_path: Path, text: str, message: str) -> None:
    with pytest.raises(ConfigurationError, match=message.replace(".", r"\.")):
        LOADER.load(write_config(tmp_path, text))


def test_knowledge_root_is_found_from_package_location(knowledge_root: Path, monkeypatch) -> None:
    monkeypatch.delenv(KNOWLEDGE_ROOT_VARIABLE, raising=False)
    assert locate_knowledge_root().resolve() == knowledge_root.resolve()


def test_environment_variable_overrides_knowledge_root(knowledge_root: Path, monkeypatch) -> None:
    monkeypatch.setenv(KNOWLEDGE_ROOT_VARIABLE, str(knowledge_root))
    assert locate_knowledge_root() == knowledge_root


def test_explicit_knowledge_root_without_norms_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError):
        locate_knowledge_root(tmp_path)


def test_form_settings_are_merged_over_the_yaml_file(tmp_path: Path) -> None:
    text = merged_config_text(
        "placement:\n  cell_size_m: 1.0\n  composition:\n    reserve_share: 0.1\n",
        {"placement": {"composition": {"enabled": False, "shrub_mass_radii_m": [4, 3]}}},
    )
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    config = RunConfigLoader().load(path)
    assert config.placement.cell_size_m == 1.0
    assert config.placement.composition.reserve_share == 0.1
    assert config.placement.composition.enabled is False
    assert config.placement.composition.shrub_mass_radii_m == (4.0, 3.0)


def test_form_settings_work_without_a_yaml_file(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(merged_config_text(None, {"species": {"tree_palette_size": 4}}), encoding="utf-8")
    assert RunConfigLoader().load(path).species.tree_palette_size == 4


def test_example_config_in_the_repository_matches_the_defaults(knowledge_root: Path) -> None:
    config = LOADER.load(knowledge_root.parent / "config" / "run-config.example.yaml")
    assert config.placement == RunConfig().placement
    assert config.design == RunConfig().design
    assert config.species == RunConfig().species
