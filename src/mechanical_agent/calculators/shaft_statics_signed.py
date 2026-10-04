"""Signed one-plane point-load statics. Positive x is A to B; +q is the chosen transverse component direction
(vertical plane: upward). Forces and reactions are positive along +q.
Shear sums left external forces; dM/dx=V. In the vertical plane +M is
sagging. A downward 1000 N load is -1000 N. CLI negative loads use --load=-1000@200.
"""
import argparse
from collections.abc import Sequence
from dataclasses import asdict, dataclass
import json
import math

MODEL_ID = "simply_supported_signed_multi_point_load_v1"
SIGN_CONVENTION = "x A-to-B; +q is chosen transverse direction (vertical plane: upward); forces/reactions positive +q; V=sum(left external forces); dM/dx=V; +M follows this derivative (vertical plane: sagging)"
UNITS = {"force": "N", "position": "mm", "moment": "N*mm", "converted_moment": "N*m"}

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
class MomentStation:
    position_mm: float
    moment_nmm: float

@dataclass(frozen=True)
class MomentRegion:
    x_start_mm: float
    x_end_mm: float

@dataclass(frozen=True)
class SignedStaticsResult:
    model_id: str
    span_mm: float
    loads: list[PointLoad]
    total_load_n: float
    reaction_a_n: float
    reaction_b_n: float
    stations: list[MomentStation]
    segments: list[StaticsSegment]
    signed_max_bending_moment_nmm: float
    signed_min_bending_moment_nmm: float
    critical_bending_moment_nmm: float
    critical_bending_moment_nm: float
    critical_moment_regions: list[MomentRegion]
    sign_convention: str
    units: dict[str, str]
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

def calculate_simply_supported_signed_point_loads(
    span_mm: float, loads: Sequence[PointLoad]
) -> SignedStaticsResult:
    """Allow empty or zero-force loads; keep coincident loads separate."""
    span = _finite_float("span_mm", span_mm)
    if span <= 0:
        raise ValueError("span_mm must be greater than 0")
    if isinstance(loads, (str, bytes)) or not isinstance(loads, Sequence):
        raise ValueError("loads must be a sequence of PointLoad")
    normalized = []
    for i, load in enumerate(loads):
        if not isinstance(load, PointLoad):
            raise ValueError(f"loads[{i}] must be a PointLoad")
        force = _finite_float(f"loads[{i}].load_n", load.load_n)
        position = _finite_float(f"loads[{i}].position_mm", load.position_mm)
        if not 0 <= position <= span:
            raise ValueError(f"loads[{i}].position_mm must be between 0 and span_mm")
        normalized.append(PointLoad(force, position))
    normalized.sort(key=lambda load: load.position_mm)
    total = math.fsum(load.load_n for load in normalized)
    reaction_b = -math.fsum(load.load_n * (load.position_mm / span) for load in normalized)
    reaction_a = -total - reaction_b
    if not all(math.isfinite(x) for x in (total, reaction_a, reaction_b)):
        raise ValueError("calculated reactions must be finite")
    events = sorted({0.0, span, *(load.position_mm for load in normalized)})

    def moment_at(x: float) -> float:
        return math.fsum([reaction_a * x] + [
            load.load_n * (x - load.position_mm)
            for load in normalized if load.position_mm <= x
        ])

    moments = [moment_at(x) for x in events]
    segments = []
    for i, (start, end) in enumerate(zip(events, events[1:])):
        shear = math.fsum([reaction_a] + [
            load.load_n for load in normalized if load.position_mm <= start
        ])
        segments.append(StaticsSegment(start, end, shear, moments[i], moments[i + 1]))
    maximum, minimum = max(moments), min(moments)
    critical = max(abs(maximum), abs(minimum))
    critical_nm = critical / 1000
    if not all(math.isfinite(x) for x in (*moments, critical_nm, *(s.shear_n for s in segments))):
        raise ValueError("calculated shear or moment must be finite")

    def peak(value: float) -> bool:
        return math.isclose(abs(value), critical, rel_tol=1e-12, abs_tol=0)

    regions = []
    for i, (position, value) in enumerate(zip(events, moments)):
        if not peak(value):
            continue
        end = position
        if (i < len(segments) and peak(moments[i + 1])
                and math.isclose(segments[i].shear_n, 0, rel_tol=1e-12, abs_tol=1e-12)):
            end = events[i + 1]
        if regions and regions[-1].x_end_mm == position:
            regions[-1] = MomentRegion(regions[-1].x_start_mm, end)
        else:
            regions.append(MomentRegion(position, end))
    return SignedStaticsResult(
        MODEL_ID, span, normalized, total, reaction_a, reaction_b,
        [MomentStation(x, m) for x, m in zip(events, moments)], segments,
        maximum, minimum, critical, critical_nm, regions, SIGN_CONVENTION, UNITS,
        "RA+RB+sum(Fi)=0; RB*L+sum(Fi*xi)=0; V=RA+sum(Fi left); M=RA*x+sum(Fi*max(0,x-xi))",
        ["simple supports at x=0 and x=L", "one transverse plane, static point forces only",
         "positive force/reaction along chosen +q; in a vertical plane +q upward gives sagging +M",
         "loads on or between supports, including coincident and zero loads",
         "no distributed loads, applied couples, overhangs, axial loads, two-plane bending, variable EI, deflection, fatigue, or dynamics"],
    )

def _parse_load(raw: str) -> PointLoad:
    parts = raw.split("@")
    if len(parts) != 2 or not all(part.strip() for part in parts):
        raise argparse.ArgumentTypeError("--load must have format SIGNED_FORCE_N@POSITION_MM")
    try:
        return PointLoad(float(parts[0]), float(parts[1]))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--load must have numeric format SIGNED_FORCE_N@POSITION_MM") from exc

def main() -> None:
    parser = argparse.ArgumentParser(description="Signed one-plane simply supported point-load statics")
    parser.add_argument("--span-mm", type=float, required=True)
    parser.add_argument("--load", type=_parse_load, action="append", default=[])
    args = parser.parse_args()
    try:
        result = calculate_simply_supported_signed_point_loads(args.span_mm, args.load)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(asdict(result), allow_nan=False))

if __name__ == "__main__":
    main()
