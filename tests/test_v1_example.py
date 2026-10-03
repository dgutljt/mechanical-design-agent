"""Regression contract for the committed V1 example."""

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "v1-shaft-analysis"
GOLDEN = ("shear_force_diagram.svg", "bending_moment_diagram.svg", "shaft_analysis_report.html")


def test_v1_input_and_expected_contract():
    input_data = json.loads((EXAMPLE / "input.json").read_text(encoding="utf-8"))
    assert input_data == {
        "power_kw": 5.5, "speed_rpm": 960, "span_mm": 600.0,
        "loads": [{"load_n": 1000.0, "position_mm": 200.0},
                  {"load_n": 500.0, "position_mm": 450.0}],
        "allowable_shear_mpa": 40.0,
    }
    expected = json.loads((EXAMPLE / "expected_results.json").read_text(encoding="utf-8"))
    assert expected == {
        "torque_nm": 54.713541666666664,
        "reaction_a_n": 791.6666666666667,
        "reaction_b_n": 708.3333333333333,
        "max_bending_moment_nm": 158.33333333333334,
        "max_moment_regions": [{"x_start_mm": 200.0, "x_end_mm": 200.0}],
        "min_diameter_mm": 27.732717671613003,
    }


def test_v1_demo_verify_and_generated_artifacts(tmp_path):
    output = tmp_path / "demo"
    completed = subprocess.run(
        [sys.executable, str(EXAMPLE / "run_demo.py"), "--verify", "--output-dir", str(output)],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert completed.returncode == 0, completed.stderr
    expected = json.loads((EXAMPLE / "expected_results.json").read_text(encoding="utf-8"))
    actual = json.loads((output / "results.json").read_text(encoding="utf-8"))
    assert {key: actual[key] for key in expected} == expected
    assert actual["review_status"] == dict.fromkeys(
        ("torque", "statics", "combined", "verified_handoff"), "PASS"
    )
    for name in GOLDEN:
        assert (output / name).read_bytes() == (EXAMPLE / "expected" / name).read_bytes()
    for name in ("torque.json", "statics.json", "strength_workflow.json",
                 "torque_provenance.json", "statics_provenance.json",
                 "combined_provenance.json", "diagram_manifest.json"):
        assert (output / name).is_file()
