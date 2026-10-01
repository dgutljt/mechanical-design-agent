"""Theoretical solid-shaft sizing under steady bending and torsion."""

import argparse
from dataclasses import asdict, dataclass
import json
import math


@dataclass(frozen=True, slots=True)
class CombinedShaftResult:
    bending_moment_nm: float
    bending_moment_nmm: float
    torque_nm: float
    torque_nmm: float
    allowable_shear_mpa: float
    combined_load_term_nmm: float
    min_diameter_mm: float
    criterion: str
    formula: str
    assumptions: list[str]


def calculate_solid_shaft_min_diameter_combined(
    bending_moment_nm: float, torque_nm: float, allowable_shear_mpa: float
) -> CombinedShaftResult:
    """Return the theoretical minimum diameter in mm under the Tresca criterion.

    Moments are converted from N·m to N·mm; MPa is N/mm². This elastic,
    steady-load strength result is not a final shaft design diameter.
    """
    if not math.isfinite(bending_moment_nm):
        raise ValueError("bending_moment_nm must be finite")
    if not math.isfinite(torque_nm):
        raise ValueError("torque_nm must be finite")
    if not math.isfinite(allowable_shear_mpa):
        raise ValueError("allowable_shear_mpa must be finite")
    if bending_moment_nm < 0:
        raise ValueError("bending_moment_nm must be non-negative")
    if torque_nm < 0:
        raise ValueError("torque_nm must be non-negative")
    if allowable_shear_mpa <= 0:
        raise ValueError("allowable_shear_mpa must be greater than 0")

    bending_moment_nm = float(bending_moment_nm)
    torque_nm = float(torque_nm)
    allowable_shear_mpa = float(allowable_shear_mpa)
    bending_moment_nmm = bending_moment_nm * 1000
    torque_nmm = torque_nm * 1000
    if not math.isfinite(bending_moment_nmm):
        raise ValueError("converted bending_moment_nmm must be finite")
    if not math.isfinite(torque_nmm):
        raise ValueError("converted torque_nmm must be finite")

    combined_load_term_nmm = math.hypot(bending_moment_nmm, torque_nmm)
    diameter_cubed = 16 * combined_load_term_nmm / (math.pi * allowable_shear_mpa)
    min_diameter_mm = diameter_cubed ** (1 / 3)
    if not math.isfinite(min_diameter_mm):
        raise ValueError("calculated min_diameter_mm must be finite")

    return CombinedShaftResult(
        bending_moment_nm=bending_moment_nm,
        bending_moment_nmm=bending_moment_nmm,
        torque_nm=torque_nm,
        torque_nmm=torque_nmm,
        allowable_shear_mpa=allowable_shear_mpa,
        combined_load_term_nmm=combined_load_term_nmm,
        min_diameter_mm=min_diameter_mm,
        criterion="maximum shear stress (Tresca)",
        formula="d_min = (16 * sqrt(M_Nmm^2 + T_Nmm^2) / (pi * tau_allow))^(1/3)",
        assumptions=[
            "solid circular shaft",
            "elastic stress analysis",
            "steady bending moment and torque",
            "theoretical strength sizing only",
            "no fatigue or alternating loading",
            "no shock or dynamic loading",
            "no keyway, shoulders, or stress concentration",
            "no axial force",
            "no stiffness, deflection, or critical speed criterion",
            "no standard preferred diameter",
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calculate the theoretical combined-load minimum solid-shaft diameter in mm."
    )
    parser.add_argument("--bending-moment-nm", type=float, required=True)
    parser.add_argument("--torque-nm", type=float, required=True)
    parser.add_argument("--allowable-shear-mpa", type=float, required=True)
    args = parser.parse_args()
    try:
        result = calculate_solid_shaft_min_diameter_combined(
            args.bending_moment_nm, args.torque_nm, args.allowable_shear_mpa
        )
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(asdict(result), allow_nan=False))


if __name__ == "__main__":
    main()
