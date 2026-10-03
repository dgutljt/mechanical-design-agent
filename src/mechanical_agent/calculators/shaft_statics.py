"""Static reactions and maximum moment for one transverse point load."""

import argparse
from dataclasses import asdict, dataclass
import json
import math

MODEL_ID = "simply_supported_point_load_v1"


@dataclass(frozen=True, slots=True)
class ShaftStaticsResult:
    model_id: str
    load_n: float
    span_mm: float
    load_position_mm: float
    reaction_a_n: float
    reaction_b_n: float
    max_bending_moment_nmm: float
    max_bending_moment_nm: float
    max_moment_position_mm: float
    formula: str
    assumptions: list[str]


def calculate_simply_supported_point_load(
    load_n: float, span_mm: float, load_position_mm: float
) -> ShaftStaticsResult:
    """Calculate support reactions and maximum moment in a single plane.

    Inputs use N and mm. The reported reactions and moment are magnitudes.
    """
    for name, value in (
        ("load_n", load_n),
        ("span_mm", span_mm),
        ("load_position_mm", load_position_mm),
    ):
        if not math.isfinite(value):
            raise ValueError(f"{name} must be finite")

    if load_n < 0:
        raise ValueError("load_n must be non-negative")
    if span_mm <= 0:
        raise ValueError("span_mm must be greater than 0")
    if load_position_mm < 0 or load_position_mm > span_mm:
        raise ValueError("load_position_mm must be between 0 and span_mm")

    load_n = float(load_n)
    span_mm = float(span_mm)
    load_position_mm = float(load_position_mm)
    reaction_a_n = load_n * ((span_mm - load_position_mm) / span_mm)
    reaction_b_n = load_n * (load_position_mm / span_mm)
    max_bending_moment_nmm = reaction_a_n * load_position_mm
    max_bending_moment_nm = max_bending_moment_nmm / 1000
    if not all(math.isfinite(value) for value in (
        reaction_a_n,
        reaction_b_n,
        max_bending_moment_nmm,
        max_bending_moment_nm,
    )):
        raise ValueError("calculated reactions and moment must be finite")

    return ShaftStaticsResult(
        model_id=MODEL_ID,
        load_n=load_n,
        span_mm=span_mm,
        load_position_mm=load_position_mm,
        reaction_a_n=reaction_a_n,
        reaction_b_n=reaction_b_n,
        max_bending_moment_nmm=max_bending_moment_nmm,
        max_bending_moment_nm=max_bending_moment_nm,
        max_moment_position_mm=load_position_mm,
        formula="RA = F * (L - a) / L; RB = F * a / L; Mmax = RA * a",
        assumptions=[
            "simply supported shaft / beam",
            "one transverse point load",
            "one-plane static analysis",
            "supports at x = 0 and x = L",
            "load acts between the supports (including support positions)",
            "no distributed loads",
            "no axial load",
            "no applied couple moment",
            "no shaft self-weight",
            "no bearing width",
            "no dynamic effects",
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calculate simply supported shaft reactions and maximum moment."
    )
    parser.add_argument("--load-n", type=float, required=True)
    parser.add_argument("--span-mm", type=float, required=True)
    parser.add_argument("--load-position-mm", type=float, required=True)
    args = parser.parse_args()
    try:
        result = calculate_simply_supported_point_load(
            args.load_n, args.span_mm, args.load_position_mm
        )
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(asdict(result), allow_nan=False))


if __name__ == "__main__":
    main()
