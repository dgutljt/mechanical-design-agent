import copy
from dataclasses import asdict
import json
import os
import subprocess
import sys

import pytest

from mechanical_agent.calculators.shaft_statics import calculate_simply_supported_point_load
from mechanical_agent.calculators.shaft_statics_multi import (
    PointLoad, calculate_simply_supported_point_loads,
)
from mechanical_agent.calculators.torque import calculate_transmitted_torque
from mechanical_agent.workflows import verified_shaft_strength as workflow


def inputs():
    torque = asdict(calculate_transmitted_torque(5.5, 960))
    statics = asdict(calculate_simply_supported_point_loads(
        600, [PointLoad(1000, 200), PointLoad(500, 450)]
    ))
    return torque, statics


def test_happy_path_and_exact_lineage():
    torque, statics = inputs()
    result = workflow.run_verified_shaft_strength_chain(torque, statics, 40)
    assert result.workflow_id == "verified_shaft_strength_chain_v1"
    assert result.status == "PASS"
    assert result.upstream_torque_review_status == "PASS"
    assert result.upstream_statics_review_status == "PASS"
    assert result.combined_review_status == "PASS"
    assert result.torque_source_field == "torque_nm"
    assert result.bending_moment_source_field == "max_bending_moment_nm"
    assert result.torque_nm == torque["torque_nm"] == 54.713541666666664
    assert result.bending_moment_nm == statics["max_bending_moment_nm"] == 158.33333333333334
    assert result.combined_result["torque_nm"] == result.torque_nm
    assert result.combined_result["bending_moment_nm"] == result.bending_moment_nm
    assert result.combined_result["min_diameter_mm"] == 27.732717671613003


@pytest.mark.parametrize("field,value,review_field", [
    ("torque_nm", 60, "upstream_torque_review_status"),
    ("max_bending_moment_nm", 297.22222222222223, "upstream_statics_review_status"),
])
def test_tampered_upstream_never_calls_combined(monkeypatch, field, value, review_field):
    torque, statics = inputs()
    source = torque if field == "torque_nm" else statics
    source[field] = value

    def forbidden(*args):
        pytest.fail("combined calculator must not run after upstream Reviewer FAIL")

    monkeypatch.setattr(workflow, "calculate_solid_shaft_min_diameter_combined", forbidden)
    result = workflow.run_verified_shaft_strength_chain(torque, statics, 40)
    assert result.status == "FAIL"
    assert getattr(result, review_field) == "FAIL"
    assert result.combined_result is None
    assert result.combined_review_status == "NOT_RUN"
    assert result.errors


def test_wrong_registered_model_is_rejected(monkeypatch):
    torque, _ = inputs()
    statics = asdict(calculate_simply_supported_point_load(1000, 600, 200))
    monkeypatch.setattr(workflow, "calculate_solid_shaft_min_diameter_combined",
                        lambda *args: pytest.fail("wrong model reached combined calculator"))
    result = workflow.run_verified_shaft_strength_chain(torque, statics, 40)
    assert result.status == "FAIL"
    assert result.upstream_statics_review_status == "PASS"
    assert result.combined_result is None
    assert any("model_id must be" in error for error in result.errors)


def test_combined_reviewer_fail_prevents_overall_pass(monkeypatch):
    torque, statics = inputs()
    original = workflow.review_engineering_result

    def review_with_combined_failure(source):
        review = original(source)
        if source["model_id"] == workflow.COMBINED_MODEL_ID:
            review.add("injected_failure", False, "combined result rejected")
        return review

    monkeypatch.setattr(workflow, "review_engineering_result", review_with_combined_failure)
    result = workflow.run_verified_shaft_strength_chain(torque, statics, 40)
    assert result.status == "FAIL"
    assert result.combined_result is not None
    assert result.combined_review_status == "FAIL"
    assert "combined Reviewer: combined result rejected" in result.errors


def run_cli(stdin, *args):
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    return subprocess.run(
        [sys.executable, "-m", "mechanical_agent.workflows.verified_shaft_strength",
         "--allowable-shear-mpa", "40", *args],
        input=stdin, text=True, capture_output=True, env=env,
    )


@pytest.mark.parametrize("stdin", [
    "", "{}\n", "{}\n{}\n{}\n", "not json\n{}\n", "[]\n{}\n",
])
def test_malformed_stdin_returns_json_fail_without_traceback(stdin):
    process = run_cli(stdin)
    output = json.loads(process.stdout)
    assert process.returncode == 2
    assert output["status"] == "FAIL"
    assert output["combined_result"] is None
    assert "Traceback" not in process.stderr


def test_cli_happy_path_and_g2_tamper():
    torque, statics = inputs()
    raw_torque = json.dumps(torque)
    raw_statics = json.dumps(statics)
    process = run_cli(raw_torque + "\n" + raw_statics + "\n")
    output = json.loads(process.stdout)
    assert process.returncode == 0
    assert output["status"] == "PASS"
    assert output["combined_result"]["min_diameter_mm"] == 27.732717671613003

    tampered = copy.deepcopy(statics)
    tampered["max_bending_moment_nm"] = 297.22222222222223
    process = run_cli(raw_torque + "\n" + json.dumps(tampered) + "\n")
    output = json.loads(process.stdout)
    assert process.returncode == 1
    assert output["status"] == "FAIL"
    assert output["upstream_statics_review_status"] == "FAIL"
    assert output["combined_result"] is None
    assert "Traceback" not in process.stderr
