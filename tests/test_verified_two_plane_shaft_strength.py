"""Exact reviewed lineage from two-plane statics into combined shaft sizing."""

from dataclasses import asdict
import inspect
import json
import math
import os
import subprocess
import sys

import pytest

from mechanical_agent.calculators.shaft_statics_multi import (
    PointLoad as UnsignedPointLoad, calculate_simply_supported_point_loads,
)
from mechanical_agent.calculators.shaft_statics_signed import PointLoad
from mechanical_agent.calculators.shaft_statics_two_plane import (
    calculate_simply_supported_two_plane_point_loads,
)
from mechanical_agent.calculators.torque import calculate_transmitted_torque
from mechanical_agent.review.engineering_result import review_engineering_result
from mechanical_agent.workflows import verified_two_plane_shaft_strength as workflow


def inputs():
    torque = asdict(calculate_transmitted_torque(5.5, 960))
    statics = asdict(calculate_simply_supported_two_plane_point_loads(
        600, [PointLoad(-1000, 200)], [PointLoad(-1000, 400)]
    ))
    return torque, statics


def test_misaligned_peaks_and_exact_downstream_lineage(monkeypatch):
    torque, statics = inputs()
    assert review_engineering_result(torque).status == "PASS"
    assert review_engineering_result(statics).status == "PASS"
    captured = []
    actual_calculator = workflow.calculate_solid_shaft_min_diameter_combined

    def capture(bending_moment_nm, torque_nm, allowable_shear_mpa):
        captured.append((bending_moment_nm, torque_nm, allowable_shear_mpa))
        return actual_calculator(bending_moment_nm, torque_nm, allowable_shear_mpa)

    monkeypatch.setattr(workflow, "calculate_solid_shaft_min_diameter_combined", capture)
    result = workflow.run_verified_two_plane_shaft_strength_chain(torque, statics, 40)
    actual = statics["critical_resultant_bending_moment_nmm"]
    wrong = math.hypot(statics["plane_1"]["critical_bending_moment_nmm"],
                       statics["plane_2"]["critical_bending_moment_nmm"])
    assert statics["plane_1"]["critical_bending_moment_nmm"] == pytest.approx(400000 / 3)
    assert statics["plane_2"]["critical_bending_moment_nmm"] == pytest.approx(400000 / 3)
    assert actual == pytest.approx(149071.19849998597)
    assert wrong == pytest.approx(188561.80831641267)
    assert actual < wrong
    assert result.workflow_id == "verified_two_plane_shaft_strength_chain_v1"
    assert result.status == "PASS"
    assert result.upstream_torque_review_status == "PASS"
    assert result.upstream_statics_review_status == "PASS"
    assert result.combined_review_status == "PASS"
    assert result.torque_model_id == torque["model_id"]
    assert result.statics_model_id == statics["model_id"]
    assert result.torque_source_field == "torque_nm"
    assert result.bending_moment_source_field == "critical_resultant_bending_moment_nm"
    assert result.torque_source_unit == result.bending_moment_source_unit == "N*m"
    assert result.torque_nm == torque["torque_nm"]
    assert result.bending_moment_nm == statics["critical_resultant_bending_moment_nm"]
    assert captured == [(statics["critical_resultant_bending_moment_nm"], torque["torque_nm"], 40)]
    assert result.combined_result["torque_nm"] == torque["torque_nm"]
    assert result.combined_result["bending_moment_nm"] == statics["critical_resultant_bending_moment_nm"]
    assert result.critical_stations == statics["critical_stations"]
    assert result.critical_regions == statics["critical_regions"]


def test_all_equal_critical_locations_and_components_preserved():
    torque, statics = inputs()
    result = workflow.run_verified_two_plane_shaft_strength_chain(torque, statics, 40)
    assert [s["position_mm"] for s in result.critical_stations] == [200, 400]
    assert result.critical_stations[0]["plane_1_moment_nmm"] != result.critical_stations[1]["plane_1_moment_nmm"]
    assert result.critical_stations[0]["plane_2_moment_nmm"] != result.critical_stations[1]["plane_2_moment_nmm"]
    assert result.critical_regions == statics["critical_regions"]
    statics["critical_stations"][0]["position_mm"] = 999
    assert result.critical_stations[0]["position_mm"] == 200


@pytest.mark.parametrize("mutate,failed_gate", [
    (lambda t, s: t.__setitem__("torque_nm", 60), "upstream_torque_review_status"),
    (lambda t, s: s.__setitem__("critical_resultant_bending_moment_nm", 188.56180831641267), "upstream_statics_review_status"),
    (lambda t, s: s["critical_stations"][0].__setitem__("position_mm", 300), "upstream_statics_review_status"),
    (lambda t, s: s["critical_stations"][0].__setitem__("plane_1_moment_nmm", 0), "upstream_statics_review_status"),
    (lambda t, s: s["critical_regions"][0].__setitem__("x_end_mm", 300), "upstream_statics_review_status"),
])
def test_upstream_tampering_stops_before_combined(monkeypatch, mutate, failed_gate):
    torque, statics = inputs()
    mutate(torque, statics)
    monkeypatch.setattr(workflow, "calculate_solid_shaft_min_diameter_combined",
                        lambda *args: pytest.fail("combined Calculator must not execute"))
    result = workflow.run_verified_two_plane_shaft_strength_chain(torque, statics, 40)
    assert result.status == "FAIL"
    assert getattr(result, failed_gate) == "FAIL"
    assert result.combined_result is None
    assert result.combined_review_status == "NOT_RUN"
    assert result.errors


def test_old_or_signed_single_plane_model_is_rejected(monkeypatch):
    torque, _ = inputs()
    wrong = asdict(calculate_simply_supported_point_loads(
        600, [UnsignedPointLoad(1000, 200)]
    ))
    monkeypatch.setattr(workflow, "calculate_solid_shaft_min_diameter_combined",
                        lambda *args: pytest.fail("wrong model reached Calculator"))
    result = workflow.run_verified_two_plane_shaft_strength_chain(torque, wrong, 40)
    assert result.status == "FAIL"
    assert result.upstream_statics_review_status == "PASS"
    assert result.combined_result is None
    assert any("model_id must be" in error for error in result.errors)


def test_combined_reviewer_failure_keeps_workflow_failed(monkeypatch):
    torque, statics = inputs()
    original = workflow.review_engineering_result

    def reject_combined(source):
        review = original(source)
        if source["model_id"] == workflow.COMBINED_MODEL_ID:
            review.add("injected_failure", False, "combined result rejected")
        return review

    monkeypatch.setattr(workflow, "review_engineering_result", reject_combined)
    result = workflow.run_verified_two_plane_shaft_strength_chain(torque, statics, 40)
    assert result.status == "FAIL"
    assert result.combined_review_status == "FAIL"
    assert result.combined_result is not None
    assert "combined Reviewer: combined result rejected" in result.errors


def test_no_intermediate_override_inputs():
    assert list(inspect.signature(workflow.run_verified_two_plane_shaft_strength_chain).parameters) == [
        "torque_result", "two_plane_statics_result", "allowable_shear_mpa"
    ]
    torque, statics = inputs()
    with pytest.raises(TypeError):
        workflow.run_verified_two_plane_shaft_strength_chain(
            torque, statics, 40, bending_moment_nm=999
        )


def test_cli_exact_lineage_and_malformed_input():
    torque, statics = inputs()
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    command = [sys.executable, "-m", "mechanical_agent.workflows.verified_two_plane_shaft_strength",
               "--allowable-shear-mpa", "40"]
    process = subprocess.run(command, input=json.dumps(torque) + "\n" + json.dumps(statics) + "\n",
                             text=True, capture_output=True, env=env)
    output = json.loads(process.stdout)
    assert process.returncode == 0
    assert output["status"] == "PASS"
    assert output["combined_result"]["torque_nm"] == torque["torque_nm"]
    assert output["combined_result"]["bending_moment_nm"] == statics["critical_resultant_bending_moment_nm"]
    assert output["critical_stations"] == statics["critical_stations"]
    malformed = subprocess.run(command, input="{}\n", text=True, capture_output=True, env=env)
    assert malformed.returncode == 2
    assert json.loads(malformed.stdout)["status"] == "FAIL"
    assert "Traceback" not in malformed.stderr


@pytest.mark.parametrize("factory,mutate", [
    (lambda: asdict(calculate_transmitted_torque(5.5, 960)),
     lambda v: v.__setitem__("power_kw", [])),
    (lambda: asdict(calculate_simply_supported_point_loads(600, [UnsignedPointLoad(1000, 200)])),
     lambda v: v["loads"][0].__setitem__("load_n", [])),
    (lambda: asdict(workflow.calculate_solid_shaft_min_diameter_combined(100, 50, 40)),
     lambda v: v.__setitem__("bending_moment_nm", [])),
])
def test_pre_13c_reviewer_malformed_payloads_fail_cleanly(factory, mutate):
    value = factory()
    assert review_engineering_result(value).status == "PASS"
    mutate(value)
    assert review_engineering_result(value).status == "FAIL"
