import json
import math
import subprocess
import sys
from dataclasses import asdict

import pytest

from mechanical_agent.calculators.shaft_combined import (
    calculate_solid_shaft_min_diameter_combined,
)
from mechanical_agent.calculators.shaft_torsion import (
    calculate_solid_shaft_min_diameter,
)


MODULE = "mechanical_agent.calculators.shaft_combined"


def calculate(bending_moment_nm, torque_nm, allowable_shear_mpa):
    return calculate_solid_shaft_min_diameter_combined(
        bending_moment_nm, torque_nm, allowable_shear_mpa
    )


def test_combined_load_result_and_json_structure():
    result = calculate(100, 50, 40)
    expected_term = math.hypot(100_000, 50_000)
    expected_mm = (16 * expected_term / (math.pi * 40)) ** (1 / 3)

    assert result.min_diameter_mm == pytest.approx(expected_mm)
    assert result.bending_moment_nmm == 100_000.0
    assert result.torque_nmm == 50_000.0
    assert result.combined_load_term_nmm == pytest.approx(expected_term)
    assert result.criterion == "maximum shear stress (Tresca)"
    assert result.model_id == "solid_shaft_combined_tresca_v1"
    assert "solid circular shaft" in result.assumptions
    assert "steady bending moment and torque" in result.assumptions
    assert "M_Nmm" in result.formula
    assert "T_Nmm" in result.formula
    assert json.loads(json.dumps(asdict(result), allow_nan=False)) == asdict(result)


def test_zero_bending_matches_independent_pure_torsion_calculator():
    torque_nm = 54.713541666666664
    combined = calculate(0, torque_nm, 30)
    pure_torsion = calculate_solid_shaft_min_diameter(torque_nm, 30)

    assert combined.min_diameter_mm == pure_torsion.min_diameter_mm
    assert combined.min_diameter_mm == pytest.approx(21.02073486234278)


def test_zero_torque_pure_bending_limit():
    result = calculate(100, 0, 50)
    expected_mm = (16 * 100_000 / (math.pi * 50)) ** (1 / 3)

    assert result.min_diameter_mm == pytest.approx(expected_mm)
    assert result.min_diameter_mm == pytest.approx(21.677042805571556)


@pytest.mark.parametrize("bending_moment_nm, torque_nm, allowable_shear_mpa", [
    (100, 50, 40),
    (100, 0, 50),
    (0, 54.713541666666664, 30),
])
def test_inverse_stress_reaches_allowable_value(
    bending_moment_nm, torque_nm, allowable_shear_mpa
):
    result = calculate(bending_moment_nm, torque_nm, allowable_shear_mpa)
    diameter_cubed = result.min_diameter_mm**3
    sigma_b = 32 * result.bending_moment_nmm / (math.pi * diameter_cubed)
    tau_t = 16 * result.torque_nmm / (math.pi * diameter_cubed)
    tau_eq = math.hypot(tau_t, sigma_b / 2)

    assert tau_eq == pytest.approx(allowable_shear_mpa)


def test_zero_load_has_zero_theoretical_diameter():
    result = calculate(0, 0, 40)

    assert result.combined_load_term_nmm == 0.0
    assert result.min_diameter_mm == 0.0


def test_monotonicity():
    baseline = calculate(100, 50, 40).min_diameter_mm

    assert calculate(110, 50, 40).min_diameter_mm >= baseline
    assert calculate(100, 60, 40).min_diameter_mm >= baseline
    assert calculate(100, 50, 30).min_diameter_mm >= baseline


@pytest.mark.parametrize("bending_moment_nm, torque_nm, allowable_shear_mpa, message", [
    (-1, 50, 40, "bending_moment_nm must be non-negative"),
    (100, -1, 40, "torque_nm must be non-negative"),
    (100, 50, 0, "allowable_shear_mpa must be greater than 0"),
    (100, 50, -1, "allowable_shear_mpa must be greater than 0"),
    (math.nan, 50, 40, "bending_moment_nm must be finite"),
    (math.inf, 50, 40, "bending_moment_nm must be finite"),
    (100, math.nan, 40, "torque_nm must be finite"),
    (100, math.inf, 40, "torque_nm must be finite"),
    (100, 50, math.nan, "allowable_shear_mpa must be finite"),
    (100, 50, math.inf, "allowable_shear_mpa must be finite"),
])
def test_invalid_inputs_are_rejected(
    bending_moment_nm, torque_nm, allowable_shear_mpa, message
):
    with pytest.raises(ValueError, match=message):
        calculate(bending_moment_nm, torque_nm, allowable_shear_mpa)


def test_conversion_overflow_is_rejected():
    with pytest.raises(ValueError, match="converted bending_moment_nmm must be finite"):
        calculate(1e308, 50, 40)
    with pytest.raises(ValueError, match="converted torque_nmm must be finite"):
        calculate(100, 1e308, 40)


def test_cli_outputs_parseable_json():
    completed = subprocess.run(
        [sys.executable, "-m", MODULE, "--bending-moment-nm", "100",
         "--torque-nm", "50", "--allowable-shear-mpa", "40"],
        capture_output=True,
        text=True,
        check=True,
    )

    result = json.loads(completed.stdout)
    assert result["model_id"] == "solid_shaft_combined_tresca_v1"
    assert result["min_diameter_mm"] == pytest.approx(24.235670632215378)
    assert result["combined_load_term_nmm"] == pytest.approx(math.hypot(100_000, 50_000))
    assert completed.stderr == ""


def test_cli_invalid_input_has_clean_error():
    completed = subprocess.run(
        [sys.executable, "-m", MODULE, "--bending-moment-nm", "100",
         "--torque-nm", "50", "--allowable-shear-mpa", "0"],
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert completed.stdout == ""
    assert "allowable_shear_mpa must be greater than 0" in completed.stderr
    assert "Traceback" not in completed.stderr
