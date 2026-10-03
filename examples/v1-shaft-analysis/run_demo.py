"""Reproduce the reviewed V1 shaft-analysis example without an LLM or DSH."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

EXAMPLE_DIR = Path(__file__).resolve().parent
REPO_ROOT = EXAMPLE_DIR.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from mechanical_agent.calculators.torque import calculate_transmitted_torque
from mechanical_agent.calculators.shaft_statics_multi import PointLoad, calculate_simply_supported_point_loads
from mechanical_agent.knowledge_registry import resolve_model_provenance
from mechanical_agent.presentation.shaft_diagrams import render_shaft_statics_diagrams
from mechanical_agent.reporting.shaft_analysis_report import build_shaft_analysis_report
from mechanical_agent.review.engineering_result import review_engineering_result
from mechanical_agent.workflows.verified_shaft_strength import run_verified_shaft_strength_chain


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def run_demo(output_dir: Path) -> dict:
    data = json.loads((EXAMPLE_DIR / "input.json").read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)

    torque = asdict(calculate_transmitted_torque(data["power_kw"], data["speed_rpm"]))
    torque_review = review_engineering_result(torque)
    if torque_review.status != "PASS":
        raise RuntimeError(f"torque Reviewer: {torque_review.errors}")
    statics_object = calculate_simply_supported_point_loads(
        data["span_mm"], [PointLoad(**load) for load in data["loads"]]
    )
    statics = asdict(statics_object)
    statics_review = review_engineering_result(statics)
    if statics_review.status != "PASS":
        raise RuntimeError(f"statics Reviewer: {statics_review.errors}")
    workflow = run_verified_shaft_strength_chain(torque, statics, data["allowable_shear_mpa"])
    if workflow.status != "PASS" or workflow.combined_review_status != "PASS":
        raise RuntimeError(f"Verified Handoff: {workflow.errors}")

    provenance = {
        "torque": resolve_model_provenance(torque["model_id"]),
        "statics": resolve_model_provenance(statics["model_id"]),
        "combined": resolve_model_provenance(workflow.combined_result["model_id"]),
    }
    diagrams = render_shaft_statics_diagrams(statics_object, output_dir)
    build_shaft_analysis_report(
        torque_result=torque,
        statics_result=statics,
        verified_strength_result=workflow,
        torque_provenance=provenance["torque"],
        statics_provenance=provenance["statics"],
        combined_provenance=provenance["combined"],
        diagram_artifacts=diagrams,
        output_path=output_dir / "shaft_analysis_report.html",
    )

    artifacts = {
        "torque.json": torque,
        "statics.json": statics,
        "strength_workflow.json": asdict(workflow),
        "torque_provenance.json": provenance["torque"],
        "statics_provenance.json": provenance["statics"],
        "combined_provenance.json": provenance["combined"],
        "diagram_manifest.json": asdict(diagrams),
    }
    for name, payload in artifacts.items():
        _write_json(output_dir / name, payload)

    results = {
        "torque_nm": torque["torque_nm"],
        "reaction_a_n": statics["reaction_a_n"],
        "reaction_b_n": statics["reaction_b_n"],
        "max_bending_moment_nm": statics["max_bending_moment_nm"],
        "max_moment_regions": statics["max_moment_regions"],
        "min_diameter_mm": workflow.combined_result["min_diameter_mm"],
        "review_status": {
            "torque": torque_review.status,
            "statics": statics_review.status,
            "combined": workflow.combined_review_status,
            "verified_handoff": workflow.status,
        },
    }
    _write_json(output_dir / "results.json", results)
    return results


def verify(output_dir: Path, results: dict) -> None:
    expected = json.loads((EXAMPLE_DIR / "expected_results.json").read_text(encoding="utf-8"))
    for field, value in expected.items():
        if results[field] != value:
            raise ValueError(f"results mismatch: {field}")
    if any(status != "PASS" for status in results["review_status"].values()):
        raise ValueError("review status mismatch")
    for name in ("shear_force_diagram.svg", "bending_moment_diagram.svg", "shaft_analysis_report.html"):
        if (output_dir / name).read_bytes() != (EXAMPLE_DIR / "expected" / name).read_bytes():
            raise ValueError(f"golden bytes mismatch: {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=EXAMPLE_DIR / "generated")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    try:
        results = run_demo(args.output_dir)
        if args.verify:
            verify(args.output_dir, results)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        parser.exit(1, f"Demo failed: {exc}\n")
    print(f"Demo {'verified' if args.verify else 'generated'}: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
