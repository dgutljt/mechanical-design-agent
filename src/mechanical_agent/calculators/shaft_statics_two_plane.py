"""Two orthogonal signed point-load planes; same-station resultant bending.

+x runs A to B, plane 1 force is +y and plane 2 force is +z. The
signed scalar moments from the one-plane calculator map to physical
components M_z = plane_1_moment and M_y = -plane_2_moment, using
the x cross transverse-force convention.
"""
from collections.abc import Sequence
from dataclasses import asdict, dataclass
import math

from mechanical_agent.calculators.shaft_statics_signed import (
    PointLoad, SignedStaticsResult, calculate_simply_supported_signed_point_loads,
)

MODEL_ID = "simply_supported_two_plane_point_load_v1"
COORDINATE_CONVENTION = (
    "+x A-to-B; plane_1 loads along +y, plane_2 loads along +z; "
    "plane_1_moment is M_z, plane_2_moment is -M_y; each signed "
    "scalar follows the signed one-plane dM/dx=V convention"
)
UNITS = {"force": "N", "position": "mm", "moment": "N*mm", "converted_moment": "N*m"}


@dataclass(frozen=True)
class ResultantStation:
    position_mm: float
    plane_1_moment_nmm: float
    plane_2_moment_nmm: float
    resultant_bending_moment_nmm: float


@dataclass(frozen=True)
class CriticalRegion:
    x_start_mm: float
    x_end_mm: float


@dataclass(frozen=True)
class TwoPlaneStaticsResult:
    model_id: str
    span_mm: float
    plane_1: SignedStaticsResult
    plane_2: SignedStaticsResult
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


def _moment_at(plane: SignedStaticsResult, x: float) -> float:
    """Evaluate a reviewed one-plane piecewise-linear representation at x."""
    for station in plane.stations:
        if station.position_mm == x:
            return station.moment_nmm
    for segment in plane.segments:
        if segment.x_start_mm < x < segment.x_end_mm:
            value = math.fsum((segment.moment_start_nmm,
                               segment.shear_n * (x - segment.x_start_mm)))
            if not math.isfinite(value):
                raise ValueError("evaluated plane moment must be finite")
            return value
    raise ValueError("common station lies outside a plane's segments")


def calculate_simply_supported_two_plane_point_loads(
    span_mm: float,
    plane_1_loads: Sequence[PointLoad],
    plane_2_loads: Sequence[PointLoad],
) -> TwoPlaneStaticsResult:
    """Reuse signed statics twice and combine components only at common x."""
    plane_1 = calculate_simply_supported_signed_point_loads(span_mm, plane_1_loads)
    plane_2 = calculate_simply_supported_signed_point_loads(span_mm, plane_2_loads)
    if plane_1.span_mm != plane_2.span_mm:
        raise ValueError("plane spans must match")
    span = plane_1.span_mm
    common = sorted({0.0, span, *(s.position_mm for s in plane_1.stations),
                     *(s.position_mm for s in plane_2.stations)})
    stations = []
    for x in common:
        m1, m2 = _moment_at(plane_1, x), _moment_at(plane_2, x)
        resultant = math.hypot(m1, m2)
        if not math.isfinite(resultant):
            raise ValueError("resultant bending moment must be finite")
        stations.append(ResultantStation(x, m1, m2, resultant))
    critical = max(s.resultant_bending_moment_nmm for s in stations)
    critical_nm = critical / 1000
    if not math.isfinite(critical_nm):
        raise ValueError("converted critical bending moment must be finite")
    peaks = [s for s in stations if math.isclose(
        s.resultant_bending_moment_nmm, critical, rel_tol=1e-12, abs_tol=0)]
    regions = []
    for i, station in enumerate(stations):
        if station not in peaks:
            continue
        end = station.position_mm
        if i + 1 < len(stations) and stations[i + 1] in peaks:
            # Both scalar moments must be constant; equal endpoint norms alone
            # do not prove a resultant plateau.
            nxt = stations[i + 1]
            if (station.plane_1_moment_nmm == nxt.plane_1_moment_nmm
                    and station.plane_2_moment_nmm == nxt.plane_2_moment_nmm):
                end = nxt.position_mm
        if regions and regions[-1].x_end_mm == station.position_mm:
            regions[-1] = CriticalRegion(regions[-1].x_start_mm, end)
        else:
            regions.append(CriticalRegion(station.position_mm, end))
    return TwoPlaneStaticsResult(
        MODEL_ID, span, plane_1, plane_2, common, stations, critical,
        critical_nm, peaks, regions, COORDINATE_CONVENTION, UNITS,
        "R(x)=hypot(plane_1_moment(x),plane_2_moment(x)); critical=max(R(common events))",
        ["simple supports at x=0 and x=L", "signed point forces only in two orthogonal transverse directions",
         "common-event endpoint search is a project mathematical derivation for piecewise-linear moments",
         "no distributed loads, applied couples, overhangs, axial loads, or shaft sizing"],
    )
