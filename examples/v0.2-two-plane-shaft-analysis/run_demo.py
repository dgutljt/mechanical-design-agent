"""Verify the canonical two-plane case through the existing Native adapter."""

import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "src"))

from mechanical_agent.bridge.two_plane_workflow_adapter import process


def verify():
    request = json.loads((HERE / "input.json").read_text(encoding="utf-8"))
    expected = json.loads((HERE / "expected_results.json").read_text(encoding="utf-8"))
    response = process(request)
    assert response["ok"] is True, response
    assert response["workflow_id"] == expected["workflow_id"]
    results = response["results"]
    statics = results["statics"]
    assert results["torque"]["torque_nm"] == expected["torque_nm"]
    assert statics["plane_1"]["critical_bending_moment_nmm"] == expected["plane_1_independent_peak_nmm"]
    assert statics["plane_2"]["critical_bending_moment_nmm"] == expected["plane_2_independent_peak_nmm"]
    assert statics["critical_resultant_bending_moment_nmm"] == expected["critical_resultant_bending_moment_nmm"]
    assert statics["critical_resultant_bending_moment_nm"] == expected["critical_resultant_bending_moment_nm"]
    assert results["combined"]["min_diameter_mm"] == expected["min_diameter_mm"]
    assert response["reviews"] == expected["reviews"]

    critical = statics["critical_stations"]
    assert [station["position_mm"] for station in critical] == expected["critical_positions_mm"]
    assert [(s["plane_1_moment_nmm"], s["plane_2_moment_nmm"]) for s in critical] == [
        (133333.33333333334, 66666.66666666667),
        (66666.66666666669, 133333.33333333334),
    ]
    assert all(s["resultant_bending_moment_nmm"] == expected["critical_resultant_bending_moment_nmm"] for s in critical)
    assert statics["critical_regions"] == [
        {"x_start_mm": 200.0, "x_end_mm": 200.0},
        {"x_start_mm": 400.0, "x_end_mm": 400.0},
    ]
    lineage = response["lineage"]
    assert lineage["torque"] == {
        "source_model_id": results["torque"]["model_id"],
        "source_field": "torque_nm", "exact_value": results["torque"]["torque_nm"],
    }
    assert lineage["bending_moment"] == {
        "source_model_id": statics["model_id"],
        "source_field": "critical_resultant_bending_moment_nm",
        "exact_value": statics["critical_resultant_bending_moment_nm"],
    }
    assert lineage["critical_stations"] == critical
    assert lineage["critical_regions"] == statics["critical_regions"]
    assert results["combined"]["torque_nm"] == results["torque"]["torque_nm"]
    assert results["combined"]["bending_moment_nm"] == statics["critical_resultant_bending_moment_nm"]
    assert set(response["provenance"]) == {results[name]["model_id"] for name in ("torque", "statics", "combined")}
    print("v0.2 two-plane demo PASS: canonical outputs, three Reviewers, critical contexts, exact lineage")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="verify canonical result (default)")
    parser.parse_args()
    verify()
