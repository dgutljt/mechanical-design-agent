"""Analytic one-plane statics for a simply supported shaft with point loads."""

import argparse
from collections.abc import Sequence
from dataclasses import asdict, dataclass
import json
import math

MODEL_ID = "simply_supported_multi_point_load_v1"


@dataclass(frozen=True)
class PointLoad:
    load_n: float
    position_mm: float


@dataclass(frozen=True)
class StaticsSegment:
    x_start_mm: float
    x_end_mm: float
    shear_n: float
    moment_start_nmm: float
    moment_end_nmm: float


@dataclass(frozen=True)
class MomentRegion:
    x_start_mm: float
    x_end_mm: float


@dataclass(frozen=True)
class MultiLoadStaticsResult:
    model_id: str
    span_mm: float
    loads: list[PointLoad]
    total_load_n: float
    reaction_a_n: float
    reaction_b_n: float
    segments: list[StaticsSegment]
    max_bending_moment_nmm: float
    max_bending_moment_nm: float
    max_moment_regions: list[MomentRegion]
    formula: str
    assumptions: list[str]


def _finite_float(name: str, value: object) -> float:
    try:
        if isinstance(value, bool):
            raise TypeError
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def calculate_simply_supported_point_loads(
    span_mm: float, loads: Sequence[PointLoad]
) -> MultiLoadStaticsResult:
    """Return reactions, piecewise shear/moment, and every maximum region.

    Loads are non-negative magnitudes in N, positions and span are in mm.
    The input sequence and its PointLoad objects are never modified.
    """
    span = _finite_float("span_mm", span_mm)
    if span <= 0:
        raise ValueError("span_mm must be greater than 0")
    if isinstance(loads, (str, bytes)) or not isinstance(loads, Sequence):
        raise ValueError("loads must be a non-empty sequence of PointLoad")
    if not loads:
        raise ValueError("loads must be a non-empty sequence of PointLoad")

    normalized = []
    for index, load in enumerate(loads):
        if not isinstance(load, PointLoad):
            raise ValueError(f"loads[{index}] must be a PointLoad")
        force = _finite_float(f"loads[{index}].load_n", load.load_n)
        position = _finite_float(f"loads[{index}].position_mm", load.position_mm)
        if force < 0:
            raise ValueError(f"loads[{index}].load_n must be non-negative")
        if position < 0 or position > span:
            raise ValueError(f"loads[{index}].position_mm must be between 0 and span_mm")
        normalized.append(PointLoad(force, position))
    normalized.sort(key=lambda load: load.position_mm)

    total = math.fsum(load.load_n for load in normalized)
    # Sum Fi * (xi / L) to avoid overflowing the intermediate Fi * xi.
    reaction_b = math.fsum(load.load_n * (load.position_mm / span) for load in normalized)
    reaction_a = total - reaction_b
    if not all(math.isfinite(value) for value in (total, reaction_a, reaction_b)):
        raise ValueError("calculated reactions and moment must be finite")

    events = sorted({0.0, span, *(load.position_mm for load in normalized)})

    def moment_at(x: float) -> float:
        return math.fsum(
            [reaction_a * x]
            + [-load.load_n * (x - load.position_mm)
               for load in normalized if load.position_mm <= x]
        )

    moments = [moment_at(x) for x in events]
    segments = []
    for start, end, moment_start, moment_end in zip(
        events, events[1:], moments, moments[1:]
    ):
        shear = reaction_a - math.fsum(
            load.load_n for load in normalized if load.position_mm <= start
        )
        segments.append(StaticsSegment(start, end, shear, moment_start, moment_end))

    maximum = max(moments)
    maximum_nm = maximum / 1000
    if not all(math.isfinite(value) for value in (*moments, maximum_nm)):
        raise ValueError("calculated reactions and moment must be finite")

    def at_maximum(value: float) -> bool:
        return math.isclose(value, maximum, rel_tol=1e-12, abs_tol=0.0)

    # An interval belongs to the maximum region only when both endpoints
    # reach the maximum. Merge touching intervals and isolated peak points.
    regions = []
    for index, (position, value) in enumerate(zip(events, moments)):
        if not at_maximum(value):
            continue
        end = position
        if index + 1 < len(events) and at_maximum(moments[index + 1]):
            end = events[index + 1]
        if regions and regions[-1].x_end_mm == position:
            previous = regions[-1]
            regions[-1] = MomentRegion(previous.x_start_mm, end)
        else:
            regions.append(MomentRegion(position, end))

    return MultiLoadStaticsResult(
        model_id=MODEL_ID,
        span_mm=span,
        loads=normalized,
        total_load_n=total,
        reaction_a_n=reaction_a,
        reaction_b_n=reaction_b,
        segments=segments,
        max_bending_moment_nmm=maximum,
        max_bending_moment_nm=maximum_nm,
        max_moment_regions=regions,
        formula="RB = sum(Fi * xi) / L; RA = sum(Fi) - RB; M(x) = RA*x - sum(Fi*max(0, x-xi))",
        assumptions=[
            "simply supported at x = 0 and x = L",
            "one-plane static analysis",
            "non-negative, same-direction transverse point loads only",
            "loads within the supports, including support positions",
            "no distributed loads, applied couples, overhung loads, or dynamics",
        ],
    )


def _parse_load(raw: str) -> PointLoad:
    parts = raw.split("@")
    if len(parts) != 2 or not all(part.strip() for part in parts):
        raise argparse.ArgumentTypeError("--load must have format LOAD_N@POSITION_MM")
    try:
        return PointLoad(float(parts[0]), float(parts[1]))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "--load must have numeric format LOAD_N@POSITION_MM"
        ) from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Calculate simply supported multi-point shaft statics.")
    parser.add_argument("--span-mm", type=float, required=True)
    parser.add_argument("--load", type=_parse_load, action="append", required=True)
    args = parser.parse_args()
    try:
        result = calculate_simply_supported_point_loads(args.span_mm, args.load)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(asdict(result), allow_nan=False))


if __name__ == "__main__":
    main()
