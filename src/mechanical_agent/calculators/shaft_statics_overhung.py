"""Signed point-load statics for a shaft with one or two overhangs."""

from collections.abc import Sequence
from dataclasses import dataclass
import math
from fractions import Fraction

from mechanical_agent.calculators.shaft_statics_signed import (
    PointLoad, StaticsSegment, MomentStation, MomentRegion,
)

MODEL_ID = "two_support_overhung_signed_point_load_v1"
SIGN_CONVENTION = (
    "+x A-to-B; +q is the chosen transverse direction; forces/reactions positive +q; "
    "V=sum(left external forces); dM/dx=V; plane 1 +q=+y gives M_z=M; "
    "plane 2 +q=+z gives M_y=-M"
)
UNITS = {"force": "N", "position": "mm", "moment": "N*mm", "converted_moment": "N*m"}


@dataclass(frozen=True)
class OverhungStaticsResult:
    model_id: str
    support_span_mm: float
    left_overhang_mm: float
    right_overhang_mm: float
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


def _finite(name: str, value: object) -> float:
    try:
        if isinstance(value, bool):
            raise TypeError
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite")
    return number


def _rounded(value: Fraction) -> float:
    try:
        result = float(value)
    except OverflowError as exc:
        raise ValueError("calculated force, shear, or moment overflows") from exc
    if not math.isfinite(result):
        raise ValueError("calculated force, shear, or moment overflows")
    return result


def _exact_statics(loads, span):
    terms = [(Fraction(item.load_n), Fraction(item.position_mm)) for item in loads]
    total = sum((f for f, _ in terms), Fraction())
    rb = -sum((f * p for f, p in terms), Fraction()) / Fraction(span)
    return terms, total, -total - rb, rb


def _exact_moment(loads, span, ra, rb, position):
    x = Fraction(position)
    return (sum((f * (x - p) for f, p in loads if p <= x), Fraction())
            + (ra * x if x >= 0 else 0)
            + (rb * (x - span) if x >= span else 0))


def calculate_two_support_overhung_signed_point_loads(
    support_span_mm: float, left_overhang_mm: float, right_overhang_mm: float,
    loads: Sequence[PointLoad],
) -> OverhungStaticsResult:
    span = _finite("support_span_mm", support_span_mm)
    left = _finite("left_overhang_mm", left_overhang_mm)
    right = _finite("right_overhang_mm", right_overhang_mm)
    if span <= 0 or left < 0 or right < 0 or (left == 0 and right == 0):
        raise ValueError("requires positive support span and at least one nonzero overhang")
    end = span + right
    if not math.isfinite(end) or not math.isfinite(left + end):
        raise ValueError("shaft geometry overflows")
    if isinstance(loads, (str, bytes)) or not isinstance(loads, Sequence):
        raise ValueError("loads must be a sequence of PointLoad")
    normalized = []
    for i, load in enumerate(loads):
        if not isinstance(load, PointLoad):
            raise ValueError(f"loads[{i}] must be a PointLoad")
        force = _finite(f"loads[{i}].load_n", load.load_n)
        x = _finite(f"loads[{i}].position_mm", load.position_mm)
        if not -left <= x <= end:
            raise ValueError(f"loads[{i}].position_mm outside shaft domain")
        normalized.append(PointLoad(force, x))
    normalized.sort(key=lambda item: item.position_mm)
    # Binary floats are exact rational inputs. fsum alone cannot undo rounding
    # in Fi*xi/L or cancellation in Fi*(x-xi). Keep the small point-load model
    # exact through reactions, sections and peak selection; round only outputs.
    exact_loads, exact_total, exact_a, exact_b = _exact_statics(normalized, span)
    events = sorted({-left, 0.0, span, end,
                     *(item.position_mm for item in normalized)})
    exact_moments = [_exact_moment(exact_loads, Fraction(span), exact_a, exact_b, x)
                     for x in events]
    # This is an exact mechanics invariant, not a float residual/overflow test.
    if exact_moments[0] != 0 or exact_moments[-1] != 0:
        raise ValueError("free-end moment equilibrium failed")
    exact_shears = [sum((f for f, p in exact_loads if p <= x), Fraction())
                    + (exact_a if x >= 0 else 0)
                    + (exact_b if x >= span else 0) for x in events[:-1]]
    exact_maximum, exact_minimum = max(exact_moments), min(exact_moments)
    exact_critical = max(abs(exact_maximum), abs(exact_minimum))
    total, reaction_a, reaction_b = map(_rounded, (exact_total, exact_a, exact_b))
    moments = list(map(_rounded, exact_moments))
    shears = list(map(_rounded, exact_shears))
    maximum, minimum, critical, critical_nm = map(_rounded, (
        exact_maximum, exact_minimum, exact_critical, exact_critical / 1000))
    segments = [StaticsSegment(start, stop, shears[i], moments[i], moments[i + 1])
                for i, (start, stop) in enumerate(zip(events, events[1:]))]
    regions = []
    for i, (x, moment) in enumerate(zip(events, exact_moments)):
        if abs(moment) != exact_critical:
            continue
        stop = x
        if (i < len(segments)
                and abs(exact_moments[i + 1]) == exact_critical
                and exact_shears[i] == 0):
            stop = events[i + 1]
        if regions and regions[-1].x_end_mm == x:
            regions[-1] = MomentRegion(regions[-1].x_start_mm, stop)
        else:
            regions.append(MomentRegion(x, stop))
    return OverhungStaticsResult(
        MODEL_ID, span, left, right, normalized, total, reaction_a, reaction_b,
        [MomentStation(x, m) for x, m in zip(events, moments)], segments,
        maximum, minimum, critical, critical_nm, regions, SIGN_CONVENTION, UNITS,
        "RA+RB+sum(Fi)=0; RB*L+sum(Fi*xi)=0; V=sum(left external forces); "
        "M=sum(left force*(x-force position))",
        ["ideal simple supports at x=0 and x=L; shaft domain [-a,L+b]",
         "signed transverse point forces; no applied couples or distributed loads",
         "free ends have zero moment; support moments may be nonzero"],
    )
