"""Resolve model provenance for V0.x source checkouts and editable installs.

Wheel packaging of the registry is intentionally deferred; this module searches
ancestors of its source file for the repository's knowledge directory.
"""

import argparse
import json
from pathlib import Path
import tomllib


def find_knowledge_root(start: Path | None = None) -> Path:
    """Find knowledge/sources.toml in the start path or its ancestors."""
    location = (start or Path(__file__)).resolve()
    for ancestor in (location, *location.parents):
        candidate = ancestor / "knowledge"
        if (candidate / "sources.toml").is_file():
            return candidate
    raise FileNotFoundError("Could not find knowledge/sources.toml above the source module")


def _load_toml(path: Path) -> dict:
    with path.open("rb") as file:
        return tomllib.load(file)


def get_model_card(model_id: str) -> dict:
    """Return the registered card for a model ID, or reject an unknown ID."""
    for path in (find_knowledge_root() / "models").glob("*.toml"):
        card = _load_toml(path)
        if card["model_id"] == model_id:
            return card
    raise ValueError(f"Unknown model_id: {model_id}")


def resolve_model_provenance(model_id: str) -> dict:
    """Return a card and only the sources it names, in card order."""
    card = get_model_card(model_id)
    registry = _load_toml(find_knowledge_root() / "sources.toml")
    by_id = {source["id"]: source for source in registry["sources"]}
    try:
        sources = [by_id[source_id] for source_id in card["source_ids"]]
    except KeyError as exc:
        raise ValueError(f"Unregistered source id: {exc.args[0]}") from exc
    return {"model": card, "sources": sources}


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve registered engineering model provenance")
    parser.add_argument("--model-id", required=True)
    args = parser.parse_args()
    try:
        result = resolve_model_provenance(args.model_id)
    except (ValueError, FileNotFoundError, tomllib.TOMLDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
