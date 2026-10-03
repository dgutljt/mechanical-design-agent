"""Real calculator and tampered JSON checks for Reviewer V1."""

from dataclasses import asdict
import json
import math
import subprocess
import sys

import pytest

from mechanical_agent.calculators.torque import calculate_transmitted_torque
from mechanical_agent.calculators.shaft_torsion import calculate_solid_shaft_min_diameter
from mechanical_agent.calculators.shaft_combined import calculate_solid_shaft_min_diameter_combined
from mechanical_agent.calculators.shaft_statics import calculate_simply_supported_point_load
from mechanical_agent.calculators.shaft_statics_multi import (
    PointLoad, calculate_simply_supported_point_loads,
)
from mechanical_agent.review import ReviewResult, review_engineering_result


def torque_result():
    return asdict(calculate_transmitted_torque(5.5, 960))


def pure_result():
    return asdict(calculate_solid_shaft_min_diameter(54.713541666666664, 30))


def combined_result():
    return asdict(calculate_solid_shaft_min_diameter_combined(100, 50, 40))


def statics_result():
    return asdict(calculate_simply_supported_point_load(1000, 400, 150))


def multi_result():
    return asdict(calculate_simply_supported_point_loads(
        600, [PointLoad(1000, 200), PointLoad(500, 450)]))


@pytest.mark.parametrize("factory", [torque_result, pure_result, combined_result,
                                      statics_result, multi_result])
def test_real_calculator_result_passes(factory):
    review = review_engineering_result(factory())
    assert isinstance(review, ReviewResult)
    assert review.status == "PASS", review.errors
    assert review.errors == []
    assert review.reviewer_version == "engineering_reviewer_v1"
    assert any(check.name == "provenance_resolved" and check.passed for check in review.checks)
    assert any(check.name == "calculator_mapping" and check.passed for check in review.checks)


@pytest.mark.parametrize("factory,field,value,failed_check", [
    (torque_result, "torque_nm", 54.8, "numerical_consistency"),
    (pure_result, "min_diameter_mm", 21.5, "inverse_shear_stress"),
    (pure_result, "torque_nmm", 5471.354166666666, "torque_units"),
    (combined_result, "min_diameter_mm", 25, "inverse_equivalent_shear"),
    (combined_result, "combined_load_term_nmm", 100000, "combined_load_term"),
    (torque_result, "constant", 9549.0, "constant"),
    (combined_result, "criterion", "von Mises", "criterion"),
])
def test_tampered_results_fail(factory, field, value, failed_check):
    result = factory()
    result[field] = value
    review = review_engineering_result(result)
    assert review.status == "FAIL"
    assert any(check.name == failed_check and not check.passed for check in review.checks)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, True, "54.7"])
def test_invalid_numeric_field_fails(value):
    result = torque_result()
    result["torque_nm"] = value
    review = review_engineering_result(result)
    assert review.status == "FAIL"
    assert any(check.name == "finite_numeric_fields" and not check.passed
               for check in review.checks)


@pytest.mark.parametrize("result", [None, [], 5, {}, {"model_id": 42},
                                     {"model_id": "nonexistent_model_v999"}])
def test_untrusted_structure_and_unknown_model_fail(result):
    assert review_engineering_result(result).status == "FAIL"


def test_model_id_tamper_is_not_accepted():
    result = torque_result()
    result["model_id"] = "solid_shaft_pure_torsion_v1"
    review = review_engineering_result(result)
    assert review.status == "FAIL"
    assert any(check.name == "required_fields" and not check.passed
               for check in review.checks)


def test_provenance_mapping_tamper_fails(monkeypatch):
    from mechanical_agent.review import engineering_result

    actual_resolve = engineering_result.resolve_model_provenance

    def wrong_mapping(model_id):
        provenance = actual_resolve(model_id)
        provenance["model"]["calculator_function"] = "wrong_function"
        return provenance

    monkeypatch.setattr(engineering_result, "resolve_model_provenance", wrong_mapping)
    review = review_engineering_result(torque_result())
    assert review.status == "FAIL"
    assert any(check.name == "calculator_mapping" and not check.passed
               for check in review.checks)


def test_huge_integer_is_rejected_without_crash():
    result = torque_result()
    result["torque_nm"] = 10**400
    assert review_engineering_result(result).status == "FAIL"


@pytest.mark.parametrize("factory,field", [(torque_result, "power_kw"),
                                            (pure_result, "allowable_shear_mpa"),
                                            (combined_result, "bending_moment_nmm")])
def test_missing_required_field_fails(factory, field):
    result = factory()
    del result[field]
    assert review_engineering_result(result).status == "FAIL"


def test_zero_load_cases_and_cross_model_limit():
    pure = asdict(calculate_solid_shaft_min_diameter(0, 30))
    combined = asdict(calculate_solid_shaft_min_diameter_combined(0, 0, 40))
    assert review_engineering_result(pure).status == "PASS"
    assert review_engineering_result(combined).status == "PASS"

    combined = asdict(calculate_solid_shaft_min_diameter_combined(
        0, 54.713541666666664, 30))
    pure = pure_result()
    assert combined["min_diameter_mm"] == pure["min_diameter_mm"]
    assert review_engineering_result(combined).status == "PASS"
    assert review_engineering_result(pure).status == "PASS"
    assert combined["model_id"] != pure["model_id"]


@pytest.mark.parametrize("factory,field,value", [
    (torque_result, "power_kw", -1),
    (torque_result, "speed_rpm", 0),
    (pure_result, "allowable_shear_mpa", 0),
    (combined_result, "bending_moment_nm", -1),
])
def test_invalid_input_range_fails(factory, field, value):
    result = factory()
    result[field] = value
    assert review_engineering_result(result).status == "FAIL"


def test_real_cli_pipeline():
    calculator = subprocess.run(
        [sys.executable, "-m", "mechanical_agent.calculators.torque",
         "--power-kw", "5.5", "--speed-rpm", "960"],
        capture_output=True, text=True, check=True)
    reviewer = subprocess.run(
        [sys.executable, "-m", "mechanical_agent.review.engineering_result"],
        input=calculator.stdout, capture_output=True, text=True)
    assert reviewer.returncode == 0
    assert reviewer.stderr == ""
    assert json.loads(reviewer.stdout)["status"] == "PASS"


def test_cli_tamper_and_invalid_json_exit_codes():
    result = torque_result()
    result["torque_nm"] = 54.8
    command = [sys.executable, "-m", "mechanical_agent.review.engineering_result"]
    tampered = subprocess.run(command, input=json.dumps(result), capture_output=True, text=True)
    assert tampered.returncode == 1
    assert json.loads(tampered.stdout)["status"] == "FAIL"
    malformed = subprocess.run(command, input="{bad", capture_output=True, text=True)
    assert malformed.returncode == 2
    assert json.loads(malformed.stdout)["status"] == "FAIL"


@pytest.mark.parametrize("field,value", [
    ("reaction_a_n", 620), ("reaction_b_n", 380),
    ("max_bending_moment_nmm", 93000), ("max_bending_moment_nm", 93.0),
    ("max_moment_position_mm", 160), ("load_position_mm", 401),
    ("model_id", "transmitted_torque_v1"),
])
def test_statics_tampering_fails(field, value):
    result = statics_result()
    result[field] = value
    assert review_engineering_result(result).status == "FAIL"


@pytest.mark.parametrize("load,position", [(0, 150), (1000, 0), (1000, 400)])
def test_statics_zero_and_support_cases_pass(load, position):
    result = asdict(calculate_simply_supported_point_load(load, 400, position))
    assert review_engineering_result(result).status == "PASS"


def test_real_statics_cli_pipeline():
    calculator = subprocess.run(
        [sys.executable, "-m", "mechanical_agent.calculators.shaft_statics",
         "--load-n", "1000", "--span-mm", "400", "--load-position-mm", "150"],
        capture_output=True, text=True, check=True)
    reviewer = subprocess.run(
        [sys.executable, "-m", "mechanical_agent.review.engineering_result"],
        input=calculator.stdout, capture_output=True, text=True)
    assert reviewer.returncode == 0
    assert json.loads(reviewer.stdout)["status"] == "PASS"


@pytest.mark.parametrize("field,value", [
    ("reaction_a_n", 800), ("total_load_n", 1400),
    ("max_bending_moment_nmm", 150000), ("max_bending_moment_nm", 150),
    ("model_id", "simply_supported_point_load_v1"),
])
def test_multi_top_level_tampering_fails(field, value):
    result = multi_result()
    result[field] = value
    assert review_engineering_result(result).status == "FAIL"


@pytest.mark.parametrize("path,value", [
    (("loads", 0, "position_mm"), 210),
    (("segments", 0, "shear_n"), 900),
    (("segments", 0, "moment_start_nmm"), 100),
    (("segments", 0, "moment_end_nmm"), 100),
    (("segments", 0, "x_end_mm"), 210),
])
def test_multi_nested_tampering_fails(path, value):
    result = multi_result()
    group, index, field = path
    result[group][index][field] = value
    assert review_engineering_result(result).status == "FAIL"


def test_multi_plateau_region_tamper_fails():
    result = asdict(calculate_simply_supported_point_loads(
        600, [PointLoad(1000, 150), PointLoad(1000, 450)]))
    assert review_engineering_result(result).status == "PASS"
    assert result["max_moment_regions"] == [{"x_start_mm": 150.0, "x_end_mm": 450.0}]
    result["max_moment_regions"][0]["x_end_mm"] = 150
    assert review_engineering_result(result).status == "FAIL"


@pytest.mark.parametrize("mutation", [
    lambda result: result["loads"].reverse(),
    lambda result: result["loads"][0].update(load_n=-1),
    lambda result: result["loads"][0].update(position_mm=True),
    lambda result: result["segments"][0].update(shear_n="bad"),
    lambda result: result["max_moment_regions"].append(result["max_moment_regions"][0].copy()),
])
def test_multi_invalid_nested_structure_or_order_fails(mutation):
    result = multi_result()
    mutation(result)
    assert review_engineering_result(result).status == "FAIL"


def test_multi_support_load_and_coincident_loads_pass():
    result = asdict(calculate_simply_supported_point_loads(400, [
        PointLoad(100, 0), PointLoad(200, 150), PointLoad(300, 150), PointLoad(50, 400)]))
    assert review_engineering_result(result).status == "PASS"


def test_single_load_cross_model_review():
    old = statics_result()
    new = asdict(calculate_simply_supported_point_loads(400, [PointLoad(1000, 150)]))
    assert review_engineering_result(old).status == "PASS"
    assert review_engineering_result(new).status == "PASS"
    assert old["model_id"] != new["model_id"]
    for field in ("reaction_a_n", "reaction_b_n", "max_bending_moment_nmm"):
        assert old[field] == new[field]


def test_real_multi_statics_cli_pipeline():
    calculator = subprocess.run(
        [sys.executable, "-m", "mechanical_agent.calculators.shaft_statics_multi",
         "--span-mm", "600", "--load", "1000@200", "--load", "500@450"],
        capture_output=True, text=True, check=True)
    reviewer = subprocess.run(
        [sys.executable, "-m", "mechanical_agent.review.engineering_result"],
        input=calculator.stdout, capture_output=True, text=True)
    assert reviewer.returncode == 0, reviewer.stdout
    assert json.loads(reviewer.stdout)["status"] == "PASS"
