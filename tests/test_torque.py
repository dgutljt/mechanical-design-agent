import json
import math
import subprocess
import sys
from dataclasses import asdict

import pytest

from mechanical_agent.calculators.torque import calculate_transmitted_torque


def test_textbook_example_returns_structured_result():
    result = calculate_transmitted_torque(5.5, 960)

    assert result.torque_nm == pytest.approx(54.7135416667)
    assert asdict(result) == {
        "power_kw": 5.5,
        "speed_rpm": 960.0,
        "torque_nm": result.torque_nm,
        "formula": "T = 9550 * P / n",
        "constant": 9550.0,
    }


def test_second_example_is_easy_to_check_by_hand():
    assert calculate_transmitted_torque(1, 955).torque_nm == pytest.approx(10.0)


def test_zero_power_returns_zero_torque():
    assert calculate_transmitted_torque(0, 960).torque_nm == 0.0


@pytest.mark.parametrize("speed_rpm", [0, -960])
def test_nonpositive_speed_is_rejected(speed_rpm):
    with pytest.raises(ValueError, match="speed_rpm must be greater than 0"):
        calculate_transmitted_torque(5.5, speed_rpm)


def test_negative_power_is_rejected():
    with pytest.raises(ValueError, match="power_kw must be non-negative"):
        calculate_transmitted_torque(-5.5, 960)


@pytest.mark.parametrize("field", ["power_kw", "speed_rpm"])
@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_nonfinite_inputs_are_rejected(field, value):
    inputs = {"power_kw": 5.5, "speed_rpm": 960}
    inputs[field] = value

    with pytest.raises(ValueError, match=f"{field} must be finite"):
        calculate_transmitted_torque(**inputs)


def test_cli_outputs_parseable_json():
    completed = subprocess.run(
        [sys.executable, "-m", "mechanical_agent.calculators.torque", "--power-kw", "5.5", "--speed-rpm", "960"],
        capture_output=True,
        text=True,
        check=True,
    )

    result = json.loads(completed.stdout)
    assert result["torque_nm"] == pytest.approx(54.7135416667)
    assert result["constant"] == 9550.0
    assert completed.stderr == ""


def test_cli_invalid_speed_has_clean_error():
    completed = subprocess.run(
        [sys.executable, "-m", "mechanical_agent.calculators.torque", "--power-kw", "5.5", "--speed-rpm", "0"],
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert completed.stdout == ""
    assert "speed_rpm must be greater than 0" in completed.stderr
    assert "Traceback" not in completed.stderr
