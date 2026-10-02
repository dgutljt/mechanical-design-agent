"""Theoretical minimum diameter of a solid shaft under pure torsion."""

import argparse
from dataclasses import asdict, dataclass
import json
import math

MODEL_ID = "solid_shaft_pure_torsion_v1"


@dataclass(frozen=True, slots=True)
class ShaftTorsionResult:
    model_id: str
    torque_nm: float
    torque_nmm: float
    allowable_shear_mpa: float
    min_diameter_mm: float
    formula: str
    assumptions: list[str]


def calculate_solid_shaft_min_diameter(
    torque_nm: float, allowable_shear_mpa: float
) -> ShaftTorsionResult:
    """Return the theoretical minimum diameter in mm.

    Assumes a solid circular shaft, pure torsion only, and steady torque.
    Excludes bending, fatigue, keyways, stress concentration, shock factors,
    and stiffness criteria. This is not a final shaft design diameter.
    Torque is converted from N·m to N·mm; MPa is N/mm².
    """
    if not math.isfinite(torque_nm):
        raise ValueError("torque_nm must be finite")
    if not math.isfinite(allowable_shear_mpa):
        raise ValueError("allowable_shear_mpa must be finite")
    if torque_nm < 0:
        raise ValueError("torque_nm must be non-negative")
    if allowable_shear_mpa <= 0:
        raise ValueError("allowable_shear_mpa must be greater than 0")

    torque_nm = float(torque_nm)
    allowable_shear_mpa = float(allowable_shear_mpa)
    torque_nmm = torque_nm * 1000
    if not math.isfinite(torque_nmm):
        raise ValueError("converted torque_nmm must be finite")

    min_diameter_mm = (16 * torque_nmm / (math.pi * allowable_shear_mpa)) ** (1 / 3)
    if not math.isfinite(min_diameter_mm):
        raise ValueError("calculated min_diameter_mm must be finite")

    return ShaftTorsionResult(
        model_id=MODEL_ID,
        torque_nm=torque_nm,
        torque_nmm=torque_nmm,
        allowable_shear_mpa=allowable_shear_mpa,
        min_diameter_mm=min_diameter_mm,
        formula="d_min = (16 * T_Nmm / (pi * tau_allow))^(1/3)",
        assumptions=[
            "solid circular shaft",
            "pure torsion only",
            "steady torque",
            "no bending",
            "no fatigue",
            "no keyway",
            "no stress concentration",
            "no shock factor",
            "no stiffness criterion",
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calculate the theoretical pure-torsion minimum solid-shaft diameter in mm."
    )
    parser.add_argument("--torque-nm", type=float, required=True)
    parser.add_argument("--allowable-shear-mpa", type=float, required=True)
    args = parser.parse_args()
    try:
        result = calculate_solid_shaft_min_diameter(
            args.torque_nm, args.allowable_shear_mpa
        )
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(asdict(result), allow_nan=False))


if __name__ == "__main__":
    main()
