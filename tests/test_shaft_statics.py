import json
import math
import subprocess
import sys
from dataclasses import asdict

import pytest

from mechanical_agent.calculators.shaft_statics import (
    calculate_simply_supported_point_load,
)


MODULE = "mechanical_agent.calculators.shaft_statics"
CLOSE = {"rel_tol": 1e-12, "abs_tol": 1e-12}


@pytest.mark.parametrize("position, reaction_a, reaction_b, moment_nmm", [
    (200, 500, 500, 100_000),
    (100, 750, 250, 75_000),
    (300, 250, 750, 75_000),
])
def test_point_load_cases(position, reaction_a, reaction_b, moment_nmm):
    result = calculate_simply_supported_point_load(1000, 400, position)
    assert math.isclose(result.reaction_a_n, reaction_a, **CLOSE)
    assert math.isclose(result.reaction_b_n, reaction_b, **CLOSE)
    assert math.isclose(result.max_bending_moment_nmm, moment_nmm, **CLOSE)
    assert math.isclose(result.max_bending_moment_nm, moment_nmm / 1000, **CLOSE)
    assert result.max_moment_position_mm == position
    assert result.load_n == 1000
    assert result.span_mm == 400
    assert result.load_position_mm == position
    assert "RA" in result.formula and "RB" in result.formula
    assert len(result.assumptions) >= 11
    assert json.loads(json.dumps(asdict(result), allow_nan=False)) == asdict(result)


@pytest.mark.parametrize("load, position, reaction_a, reaction_b", [
    (0, 150, 0, 0),
    (1000, 0, 1000, 0),
    (1000, 400, 0, 1000),
])
def test_zero_load_and_support_boundaries(load, position, reaction_a, reaction_b):
    result = calculate_simply_supported_point_load(load, 400, position)
    assert result.reaction_a_n == reaction_a
    assert result.reaction_b_n == reaction_b
    assert result.max_bending_moment_nmm == 0
    assert result.max_bending_moment_nm == 0
    assert result.max_moment_position_mm == position


@pytest.mark.parametrize("load, span, position, message", [
    (-1, 400, 100, "load_n must be non-negative"),
    (1000, 0, 0, "span_mm must be greater than 0"),
    (1000, -1, 0, "span_mm must be greater than 0"),
    (1000, 400, -1, "load_position_mm must be between"),
    (1000, 400, 401, "load_position_mm must be between"),
    (math.nan, 400, 100, "load_n must be finite"),
    (1000, math.nan, 100, "span_mm must be finite"),
    (1000, 400, math.nan, "load_position_mm must be finite"),
    (math.inf, 400, 100, "load_n must be finite"),
    (1000, -math.inf, 100, "span_mm must be finite"),
    (1000, 400, math.inf, "load_position_mm must be finite"),
])
def test_invalid_inputs(load, span, position, message):
    with pytest.raises(ValueError, match=message):
        calculate_simply_supported_point_load(load, span, position)


def test_overflowing_moment_is_rejected():
    with pytest.raises(ValueError, match="calculated reactions and moment must be finite"):
        calculate_simply_supported_point_load(1e308, 1e308, 5e307)


@pytest.mark.parametrize("load, span, position", [
    (1000, 400, 200),
    (1000, 400, 100),
    (1000, 400, 300),
    (0, 400, 150),
    (1000, 400, 0),
    (1000, 400, 400),
])
def test_independent_force_and_moment_equilibrium(load, span, position):
    result = calculate_simply_supported_point_load(load, span, position)
    assert math.isclose(result.reaction_a_n + result.reaction_b_n, load, **CLOSE)
    assert math.isclose(result.reaction_b_n * span, load * position, **CLOSE)
    assert math.isclose(
        result.reaction_a_n * position, result.max_bending_moment_nmm, **CLOSE
    )
    assert math.isclose(
        result.reaction_b_n * (span - position),
        result.max_bending_moment_nmm,
        **CLOSE,
    )


def test_geometric_symmetry():
    left = calculate_simply_supported_point_load(1000, 400, 100)
    right = calculate_simply_supported_point_load(1000, 400, 300)
    assert math.isclose(left.reaction_a_n, right.reaction_b_n, **CLOSE)
    assert math.isclose(left.reaction_b_n, right.reaction_a_n, **CLOSE)
    assert math.isclose(
        left.max_bending_moment_nmm, right.max_bending_moment_nmm, **CLOSE
    )


def test_cli_outputs_parseable_json():
    completed = subprocess.run(
        [sys.executable, "-m", MODULE, "--load-n", "1000", "--span-mm", "400",
         "--load-position-mm", "150"],
        capture_output=True,
        text=True,
        check=True,
    )
    result = json.loads(completed.stdout)
    assert result["model_id"] == "simply_supported_point_load_v1"
    assert result["reaction_a_n"] == 625
    assert result["reaction_b_n"] == 375
    assert result["max_bending_moment_nmm"] == 93_750
    assert result["max_bending_moment_nm"] == 93.75
    assert result["max_moment_position_mm"] == 150
    assert completed.stderr == ""


def test_cli_invalid_input_has_clean_error():
    completed = subprocess.run(
        [sys.executable, "-m", MODULE, "--load-n", "-1", "--span-mm", "400",
         "--load-position-mm", "150"],
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert completed.stdout == ""
    assert "load_n must be non-negative" in completed.stderr
    assert "Traceback" not in completed.stderr
