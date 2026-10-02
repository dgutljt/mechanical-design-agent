"""Deterministic transmitted torque calculation."""

import argparse
from dataclasses import asdict, dataclass
import json
import math

MODEL_ID = "transmitted_torque_v1"


@dataclass(frozen=True, slots=True)
class TorqueResult:
    model_id: str
    power_kw: float
    speed_rpm: float
    torque_nm: float
    formula: str
    constant: float


def calculate_transmitted_torque(power_kw: float, speed_rpm: float) -> TorqueResult:
    """Calculate torque in N·m from power in kW and speed in r/min.

    T = P / ω and ω = 2πn / 60 give a converted constant of about
    9549.3. This project uses the common textbook approximation 9550.
    """
    if not math.isfinite(power_kw):
        raise ValueError("power_kw must be finite")
    if not math.isfinite(speed_rpm):
        raise ValueError("speed_rpm must be finite")
    if power_kw < 0:
        raise ValueError("power_kw must be non-negative")
    if speed_rpm <= 0:
        raise ValueError("speed_rpm must be greater than 0")

    power_kw = float(power_kw)
    speed_rpm = float(speed_rpm)
    constant = 9550.0
    torque_nm = constant * power_kw / speed_rpm
    if not math.isfinite(torque_nm):
        raise ValueError("calculated torque must be finite")
    return TorqueResult(MODEL_ID, power_kw, speed_rpm, torque_nm, "T = 9550 * P / n", constant)


def main() -> None:
    parser = argparse.ArgumentParser(description="Calculate transmitted torque in N·m.")
    parser.add_argument("--power-kw", type=float, required=True)
    parser.add_argument("--speed-rpm", type=float, required=True)
    args = parser.parse_args()
    try:
        result = calculate_transmitted_torque(args.power_kw, args.speed_rpm)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(asdict(result), allow_nan=False))


if __name__ == "__main__":
    main()
