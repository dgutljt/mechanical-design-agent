import importlib
import json
import math
import subprocess
import sys
from dataclasses import asdict

import pytest


MODULE = "mechanical_agent.calculators.shaft_torsion"


def calculate(torque_nm, allowable_shear_mpa):
    module = importlib.import_module(MODULE)
    return module.calculate_solid_shaft_min_diameter(torque_nm, allowable_shear_mpa)


def test_case_a_100_nm_and_50_mpa():
    result = calculate(100, 50)
    expected_mm = (16 * 100000 / (math.pi * 50)) ** (1 / 3)

    assert result.min_diameter_mm == pytest.approx(expected_mm)
    assert asdict(result) == {
        "model_id": "solid_shaft_pure_torsion_v1",
        "torque_nm": 100.0,
        "torque_nmm": 100000.0,
        "allowable_shear_mpa": 50.0,
        "min_diameter_mm": result.min_diameter_mm,
        "formula": "d_min = (16 * T_Nmm / (pi * tau_allow))^(1/3)",
        "assumptions": list(result.assumptions),
    }
    assert "solid circular shaft" in result.assumptions
    assert "pure torsion only" in result.assumptions


def test_case_b_uses_prior_torque_result():
    torque_nm = 54.713541666666664
    result = calculate(torque_nm, 30)
    expected_mm = (16 * (torque_nm * 1000) / (math.pi * 30)) ** (1 / 3)

    assert result.torque_nmm == pytest.approx(54713.541666666664)
    assert result.min_diameter_mm == pytest.approx(expected_mm)


@pytest.mark.parametrize(
    ("torque_nm", "allowable_shear_mpa"),
    [(100, 50), (54.713541666666664, 30)],
)
def test_inverse_shear_stress_matches_allowable_value(torque_nm, allowable_shear_mpa):
    result = calculate(torque_nm, allowable_shear_mpa)
    recovered_mpa = 16 * result.torque_nmm / (math.pi * result.min_diameter_mm**3)

    assert recovered_mpa == pytest.approx(allowable_shear_mpa)


def test_zero_torque_has_zero_theoretical_diameter():
    result = calculate(0, 30)

    assert result.torque_nmm == 0.0
    assert result.min_diameter_mm == 0.0


@pytest.mark.parametrize(
    ("torque_nm", "allowable_shear_mpa", "message"),
    [
        (-1, 30, "torque_nm must be non-negative"),
        (100, 0, "allowable_shear_mpa must be greater than 0"),
        (100, -1, "allowable_shear_mpa must be greater than 0"),
        (math.nan, 30, "torque_nm must be finite"),
        (math.inf, 30, "torque_nm must be finite"),
        (-math.inf, 30, "torque_nm must be finite"),
        (100, math.nan, "allowable_shear_mpa must be finite"),
        (100, math.inf, "allowable_shear_mpa must be finite"),
        (100, -math.inf, "allowable_shear_mpa must be finite"),
    ],
)
def test_invalid_inputs_are_rejected(torque_nm, allowable_shear_mpa, message):
    with pytest.raises(ValueError, match=message):
        calculate(torque_nm, allowable_shear_mpa)


def test_cli_outputs_parseable_json():
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            MODULE,
            "--torque-nm",
            "54.713541666666664",
            "--allowable-shear-mpa",
            "30",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    result = json.loads(completed.stdout)
    assert result["model_id"] == "solid_shaft_pure_torsion_v1"
    expected_mm = (16 * (54.713541666666664 * 1000) / (math.pi * 30)) ** (1 / 3)
    assert result["min_diameter_mm"] == pytest.approx(expected_mm)
    assert result["torque_nmm"] == pytest.approx(54713.541666666664)
    assert result["allowable_shear_mpa"] == 30.0
    assert isinstance(result["assumptions"], list)
    assert completed.stderr == ""


def test_cli_invalid_input_has_clean_error():
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            MODULE,
            "--torque-nm",
            "100",
            "--allowable-shear-mpa",
            "0",
        ],
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert completed.stdout == ""
    assert "allowable_shear_mpa must be greater than 0" in completed.stderr
    assert "Traceback" not in completed.stderr
