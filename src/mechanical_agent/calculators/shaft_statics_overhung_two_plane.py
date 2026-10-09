"""Orthogonal overhung shaft statics with same-position resultant bending."""

from collections.abc import Sequence
from dataclasses import dataclass
import math
from fractions import Fraction

from mechanical_agent.calculators.shaft_statics_signed import PointLoad
from mechanical_agent.calculators.shaft_statics_overhung import (
    OverhungStaticsResult, calculate_two_support_overhung_signed_point_loads,
    _exact_statics, _exact_moment, _rounded,
)
from mechanical_agent.calculators.shaft_statics_two_plane import ResultantStation, CriticalRegion

MODEL_ID = "two_support_overhung_two_plane_point_load_v1"
COORDINATE_CONVENTION = (
    "+x A-to-B; plane_1 loads along +y, plane_2 loads along +z; "
    "plane_1_moment is M_z, plane_2_moment is -M_y; each signed "
    "scalar follows dM/dx=V on shaft domain [-a,L+b]"
)
UNITS = {"force": "N", "position": "mm", "moment": "N*mm", "converted_moment": "N*m"}


@dataclass(frozen=True)
class OverhungTwoPlaneResult:
    model_id: str
    support_span_mm: float
    left_overhang_mm: float
    right_overhang_mm: float
    plane_1: OverhungStaticsResult
    plane_2: OverhungStaticsResult
    common_stations_mm: list[float]
    resultant_stations: list[ResultantStation]
    critical_resultant_bending_moment_nmm: float
    critical_resultant_bending_moment_nm: float
    critical_stations: list[ResultantStation]
    critical_regions: list[CriticalRegion]
    coordinate_convention: str
    units: dict[str, str]
    formula: str
    assumptions: list[str]



def _rounded_sqrt(square: Fraction) -> float:
    """Round an exact nonnegative square root once, to binary64 ties-to-even."""
    if square == 0:
        return 0.0
    # Locate the root's binade without converting the rational to a float.
    exponent = square.numerator.bit_length() - square.denominator.bit_length()
    if square < Fraction(2) ** exponent:
        exponent -= 1
    quantum = Fraction(2) ** max(exponent // 2 - 52, -1074)
    scaled = square / (quantum * quantum)
    lower = math.isqrt(scaled.numerator // scaled.denominator)
    # sqrt(scaled) versus lower+1/2, compared exactly after squaring.
    midpoint = scaled.denominator * (2 * lower + 1) ** 2
    comparison = 4 * scaled.numerator - midpoint
    if comparison > 0 or (comparison == 0 and lower % 2):
        lower += 1
    try:
        result = float(lower * quantum)
    except OverflowError as exc:
        raise ValueError("resultant bending moment overflows") from exc
    if not math.isfinite(result):
        raise ValueError("resultant bending moment overflows")
    return result


def calculate_two_support_overhung_two_plane_point_loads(
    support_span_mm: float, left_overhang_mm: float, right_overhang_mm: float,
    plane_1_loads: Sequence[PointLoad], plane_2_loads: Sequence[PointLoad],
) -> OverhungTwoPlaneResult:
    p1 = calculate_two_support_overhung_signed_point_loads(
        support_span_mm, left_overhang_mm, right_overhang_mm, plane_1_loads)
    p2 = calculate_two_support_overhung_signed_point_loads(
        support_span_mm, left_overhang_mm, right_overhang_mm, plane_2_loads)
    common = sorted({*(station.position_mm for station in p1.stations),
                     *(station.position_mm for station in p2.stations)})
    exact_planes = [_exact_statics(plane.loads, plane.support_span_mm)
                    for plane in (p1, p2)]
    exact_components = [tuple(_exact_moment(loads, Fraction(p1.support_span_mm), ra, rb, x)
                              for loads, _, ra, rb in exact_planes) for x in common]
    # Interpolating rounded endpoint moments loses small common-station moments
    # under cancellation. Evaluate the section exactly, including peak ranking.
    squared = [m1 * m1 + m2 * m2 for m1, m2 in exact_components]
    peak_squared = max(squared)
    stations = []
    for x, (exact_m1, exact_m2) in zip(common, exact_components):
        m1, m2 = _rounded(exact_m1), _rounded(exact_m2)
        resultant = _rounded_sqrt(exact_m1 * exact_m1 + exact_m2 * exact_m2)
        if not math.isfinite(resultant):
            raise ValueError("resultant bending moment overflows")
        stations.append(ResultantStation(x, m1, m2, resultant))
    critical = max(station.resultant_bending_moment_nmm for station in stations)
    peaks = [station for station, square in zip(stations, squared) if square == peak_squared]

    def zero_shear(plane_index, x):
        loads, _, ra, rb = exact_planes[plane_index]
        return (sum((f for f, p in loads if p <= x), Fraction())
                + (ra if x >= 0 else 0) + (rb if x >= p1.support_span_mm else 0)) == 0

    regions = []
    for i, station in enumerate(stations):
        if station not in peaks:
            continue
        stop = station.position_mm
        if i + 1 < len(stations) and stations[i + 1] in peaks:
            nxt = stations[i + 1]
            if (zero_shear(0, station.position_mm)
                    and zero_shear(1, station.position_mm)):
                stop = nxt.position_mm
        if regions and regions[-1].x_end_mm == station.position_mm:
            regions[-1] = CriticalRegion(regions[-1].x_start_mm, stop)
        else:
            regions.append(CriticalRegion(station.position_mm, stop))
    return OverhungTwoPlaneResult(
        MODEL_ID, p1.support_span_mm, p1.left_overhang_mm, p1.right_overhang_mm,
        p1, p2, common, stations, critical, _rounded_sqrt(peak_squared / 1000000), peaks, regions,
        COORDINATE_CONVENTION, UNITS,
        "M_z=m1; M_y=-m2; R(x)=hypot(m1(x),m2(x)); critical=max(R(common events))",
        ["ideal simple supports at x=0 and x=L with at least one overhang",
         "signed transverse point forces only; no applied couples or distributed loads",
         "same-position resultant; extrema occur at common event stations"],
    )
