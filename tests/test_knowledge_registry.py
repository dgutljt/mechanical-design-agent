"""Offline consistency checks for the engineering model registry."""

from importlib import import_module
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import tomllib

from mechanical_agent.knowledge_registry import (
    find_knowledge_root,
    get_model_card,
    resolve_model_provenance,
)


ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = ROOT / "knowledge"
MODEL_FILES = {
    "transmitted_torque.toml",
    "solid_shaft_pure_torsion.toml",
    "solid_shaft_combined_tresca.toml",
    "simply_supported_point_load.toml",
    "simply_supported_multi_point_load.toml",
    "simply_supported_signed_multi_point_load.toml",
}
CALCULATORS = {
    ("mechanical_agent.calculators.torque", "calculate_transmitted_torque"),
    ("mechanical_agent.calculators.shaft_torsion", "calculate_solid_shaft_min_diameter"),
    (
        "mechanical_agent.calculators.shaft_combined",
        "calculate_solid_shaft_min_diameter_combined",
    ),
    ("mechanical_agent.calculators.shaft_statics", "calculate_simply_supported_point_load"),
    ("mechanical_agent.calculators.shaft_statics_multi", "calculate_simply_supported_point_loads"),
    ("mechanical_agent.calculators.shaft_statics_signed", "calculate_simply_supported_signed_point_loads"),
}
REQUIRED_FIELDS = {
    "model_id",
    "title",
    "calculator_module",
    "calculator_function",
    "dsh_skill",
    "equation",
    "assumptions",
    "limitations",
    "source_ids",
}


def read_toml(path: Path) -> dict:
    with path.open("rb") as file:
        return tomllib.load(file)


def cards() -> list[dict]:
    return [read_toml(KNOWLEDGE / "models" / name) for name in sorted(MODEL_FILES)]


def test_sources_parse_and_have_unique_ids() -> None:
    sources = read_toml(KNOWLEDGE / "sources.toml")["sources"]
    ids = [source["id"] for source in sources]
    assert len(sources) >= 2
    assert len(ids) == len(set(ids))


def test_all_six_model_cards_parse_and_have_unique_ids() -> None:
    assert {path.name for path in (KNOWLEDGE / "models").glob("*.toml")} == MODEL_FILES
    model_ids = [card["model_id"] for card in cards()]
    assert len(model_ids) == len(set(model_ids))
    assert set(model_ids) == {
        "transmitted_torque_v1",
        "solid_shaft_pure_torsion_v1",
        "solid_shaft_combined_tresca_v1",
        "simply_supported_point_load_v1",
        "simply_supported_multi_point_load_v1",
        "simply_supported_signed_multi_point_load_v1",
    }


def test_cards_have_required_fields_and_valid_sources() -> None:
    source_ids = {source["id"] for source in read_toml(KNOWLEDGE / "sources.toml")["sources"]}
    for card in cards():
        assert REQUIRED_FIELDS <= card.keys(), card.get("model_id")
        assert card["source_ids"]
        assert set(card["source_ids"]) <= source_ids


def test_calculator_modules_functions_and_skills_exist() -> None:
    for card in cards():
        module = import_module(card["calculator_module"])
        assert callable(getattr(module, card["calculator_function"]))
        assert (ROOT / ".dsh" / "skills" / card["dsh_skill"] / "SKILL.md").is_file()


def test_every_current_calculator_has_a_card() -> None:
    mapped = {(card["calculator_module"], card["calculator_function"]) for card in cards()}
    assert mapped == CALCULATORS


def test_calculator_model_ids_match_cards_in_both_directions() -> None:
    registered = {card["model_id"] for card in cards()}
    calculator_ids = {import_module(module).MODEL_ID for module, _ in CALCULATORS}
    assert calculator_ids == registered
    for card in cards():
        assert import_module(card["calculator_module"]).MODEL_ID == card["model_id"]


def test_resolver_returns_only_referenced_sources() -> None:
    for card in cards():
        result = resolve_model_provenance(card["model_id"])
        assert result["model"] == card
        assert [source["id"] for source in result["sources"]] == card["source_ids"]
        assert result["sources"]
        assert get_model_card(card["model_id"]) == card


def test_statics_provenance_is_scoped_to_its_registered_source() -> None:
    result = resolve_model_provenance("simply_supported_point_load_v1")
    assert result["model"]["source_ids"] == ["engineering_statics_beam_equilibrium"]
    assert [source["id"] for source in result["sources"]] == ["engineering_statics_beam_equilibrium"]


def test_multi_statics_provenance_is_scoped_to_its_registered_source() -> None:
    result = resolve_model_provenance("simply_supported_multi_point_load_v1")
    assert result["model"]["source_ids"] == ["engineering_statics_beam_equilibrium"]
    assert [source["id"] for source in result["sources"]] == ["engineering_statics_beam_equilibrium"]


def test_unknown_model_is_rejected_without_traceback_by_cli() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "mechanical_agent.knowledge_registry", "--model-id", "nonexistent_model_v999"],
        capture_output=True, text=True,
    )
    assert completed.returncode != 0
    assert completed.stdout == ""
    assert "Unknown model_id: nonexistent_model_v999" in completed.stderr
    assert "Traceback" not in completed.stderr


def test_resolver_cli_outputs_parseable_json() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "mechanical_agent.knowledge_registry", "--model-id", "transmitted_torque_v1"],
        capture_output=True, text=True, check=True,
    )
    result = json.loads(completed.stdout)
    assert result["model"]["model_id"] == "transmitted_torque_v1"
    assert [source["id"] for source in result["sources"]] == ["oer_strength_materials_torsion"]
    assert completed.stderr == ""


def test_knowledge_root_search_stays_with_start_ancestors() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        nested = root / "src" / "mechanical_agent"
        nested.mkdir(parents=True)
        registry = root / "knowledge"
        registry.mkdir()
        (registry / "sources.toml").write_text("sources = []", encoding="utf-8")
        assert find_knowledge_root(nested) == registry
        (registry / "sources.toml").unlink()
        try:
            find_knowledge_root(nested)
        except FileNotFoundError as exc:
            assert "knowledge/sources.toml" in str(exc)
        else:
            raise AssertionError("Missing registry should raise FileNotFoundError")
