"""Overhung geometry, event mechanics, same-station extrema and adversarial review."""

from copy import deepcopy
from dataclasses import asdict
import math

import pytest

from mechanical_agent.calculators.shaft_statics_signed import PointLoad
from mechanical_agent.calculators.shaft_statics_overhung import (
    calculate_two_support_overhung_signed_point_loads as one,
)
from mechanical_agent.calculators.shaft_statics_overhung_two_plane import (
    calculate_two_support_overhung_two_plane_point_loads as two,
)
from mechanical_agent.knowledge_registry import resolve_model_provenance
from mechanical_agent.review.engineering_result import review_engineering_result


def checked_one(span, left, right, loads):
    value = asdict(one(span, left, right, [PointLoad(*load) for load in loads]))
    assert review_engineering_result(value).status == "PASS"
    return value


def checked_two(span, left, right, p1, p2):
    value = asdict(two(span, left, right, [PointLoad(*load) for load in p1],
                       [PointLoad(*load) for load in p2]))
    review = review_engineering_result(value)
    assert review.status == "PASS", review.errors
    return value


@pytest.mark.parametrize("left,right,loads,expected_a,expected_b", [
    (100, 0, [(-1000, -100)], 1166.6666666666667, -166.66666666666666),
    (0, 100, [(-1000, 700)], -166.66666666666674, 1166.6666666666667),
    (100, 100, [(-1000, -100), (-200, 300), (300, 700)], 1316.6666666666667, -416.6666666666667),
])
def test_overhang_sides_negative_reaction_and_free_ends(left, right, loads, expected_a, expected_b):
    value = checked_one(600, left, right, loads)
    assert value["reaction_a_n"] == pytest.approx(expected_a)
    assert value["reaction_b_n"] == pytest.approx(expected_b)
    assert value["stations"][0]["moment_nmm"] == pytest.approx(0)
    assert value["stations"][-1]["moment_nmm"] == pytest.approx(0)
    assert value["stations"][0]["position_mm"] == -left
    assert value["stations"][-1]["position_mm"] == 600 + right


def test_support_loads_interior_loads_and_nonzero_support_moment():
    value = checked_one(600, 100, 100,
                        [(-1000, -100), (-100, 0), (200, 300), (-300, 600), (500, 700)])
    stations = {s["position_mm"]: s["moment_nmm"] for s in value["stations"]}
    assert stations[0] == pytest.approx(-100000)
    assert stations[600] == pytest.approx(50000)
    assert stations[-100] == pytest.approx(0)
    assert stations[700] == pytest.approx(0)


def test_coincident_opposing_zero_and_empty_loads():
    value = checked_one(600, 100, 0, [(500, -100), (-500, -100), (0, 300)])
    assert len(value["loads"]) == 3
    assert value["total_load_n"] == 0
    assert value["critical_bending_moment_nmm"] == 0
    empty = checked_one(600, 100, 0, [])
    assert empty["critical_moment_regions"] == [{"x_start_mm": -100, "x_end_mm": 600}]
    result = checked_two(600, 100, 0, [], [(-500, 300)])
    assert all(s["plane_1_moment_nmm"] == 0 for s in result["resultant_stations"])


def test_nearby_floating_positions_remain_distinct_events():
    x = 200.0
    nearby = math.nextafter(x, math.inf)
    value = checked_two(600, 100, 100, [(-1000, x)], [(1000, nearby)])
    assert x != nearby
    assert x in value["common_stations_mm"]
    assert nearby in value["common_stations_mm"]
    assert value["common_stations_mm"].index(nearby) == value["common_stations_mm"].index(x) + 1


def test_misaligned_peaks_ties_and_true_plateau():
    value = checked_two(600, 100, 100, [(-1000, 200)], [(-1000, 400)])
    separate = math.hypot(value["plane_1"]["critical_bending_moment_nmm"],
                          value["plane_2"]["critical_bending_moment_nmm"])
    assert value["critical_resultant_bending_moment_nmm"] < separate
    tied = checked_two(600, 100, 100,
                       [(-1000, 100), (2000, 200), (-2000, 400), (1000, 500)], [])
    assert [s["position_mm"] for s in tied["critical_stations"]] == [200, 400]
    assert tied["critical_regions"] == [
        {"x_start_mm": 200, "x_end_mm": 200},
        {"x_start_mm": 400, "x_end_mm": 400},
    ]
    plateau = checked_two(600, 100, 100, [(-1000, 200), (-1000, 400)], [])
    assert plateau["critical_regions"] == [{"x_start_mm": 200, "x_end_mm": 400}]
    zero = checked_two(600, 100, 100, [], [])
    assert zero["critical_regions"] == [{"x_start_mm": -100, "x_end_mm": 700}]


@pytest.mark.parametrize("span,left,right,loads", [
    (0, 1, 0, []), (600, 0, 0, []), (600, -1, 2, []),
    (600, 100, -1, []), (float("nan"), 1, 0, []),
    (600, float("inf"), 0, []), (600, 100, 0, [(1, -101)]),
    (600, 0, 100, [(1, 701)]), (600, 100, 0, [(float("nan"), 0)]),
    (600, 100, 0, [(1, float("inf"))]),
    (1e308, 1, 1e308, []), (600, 100, 0, [(1e308, 300), (1e308, 300)]),
])
def test_invalid_geometry_loads_and_overflow(span, left, right, loads):
    with pytest.raises(ValueError):
        one(span, left, right, [PointLoad(*item) for item in loads])


def test_invalid_plane_shape_and_resultant_overflow():
    with pytest.raises(ValueError):
        two(600, 100, 0, "bad", [])
    with pytest.raises(ValueError):
        two(600, 100, 0, [PointLoad(1e308, -100)], [PointLoad(1e308, -100)])


@pytest.mark.parametrize("mutation", [
    lambda v: v["plane_1"].__setitem__("reaction_a_n", 0),
    lambda v: v["plane_1"]["stations"][1].__setitem__("moment_nmm", 0),
    lambda v: v["plane_1"]["segments"][0].__setitem__("shear_n", 0),
    lambda v: v["plane_1"]["stations"][-1].__setitem__("moment_nmm", 1),
    lambda v: v["plane_1"]["stations"][1].__setitem__("position_mm", 1e-13),
    lambda v: v["common_stations_mm"].pop(1),
    lambda v: v["resultant_stations"][1].__setitem__("plane_1_moment_nmm", 0),
    lambda v: v["resultant_stations"][1].__setitem__("resultant_bending_moment_nmm", 0),
    lambda v: v.__setitem__("critical_resultant_bending_moment_nmm", 0),
    lambda v: v["critical_stations"][0].__setitem__("position_mm", 1),
    lambda v: v["critical_regions"][0].__setitem__("x_end_mm", 1),
    lambda v: v.__setitem__("units", {"moment": "N*m"}),
    lambda v: v["plane_1"].__setitem__("model_id", "fake"),
])
def test_reviewer_rejects_forged_two_plane_json(mutation):
    value = checked_two(600, 100, 100, [(-1000, -100), (-500, 200)], [(300, 400)])
    forged = deepcopy(value)
    mutation(forged)
    assert review_engineering_result(forged).status == "FAIL"


@pytest.mark.parametrize("mutation", [
    lambda v: v.__setitem__("reaction_b_n", 1),
    lambda v: v["segments"][0].__setitem__("moment_end_nmm", 0),
    lambda v: v["stations"][1].__setitem__("moment_nmm", 0),
    lambda v: v["critical_moment_regions"][0].__setitem__("x_start_mm", 1),
])
def test_reviewer_rejects_forged_one_plane_json(mutation):
    value = checked_one(600, 100, 100, [(-1000, -100), (-500, 200)])
    forged = deepcopy(value)
    mutation(forged)
    assert review_engineering_result(forged).status == "FAIL"


def test_model_cards_resolve_registered_source():
    for model_id in ("two_support_overhung_signed_point_load_v1",
                     "two_support_overhung_two_plane_point_load_v1"):
        provenance = resolve_model_provenance(model_id)
        assert [s["id"] for s in provenance["sources"]] == ["engineering_statics_beam_equilibrium"]
        assert "project mathematical derivation" in provenance["model"]["derivation"]


@pytest.mark.parametrize("force,position,peak", [
    (-20000, -100, 2000000),  # P1-A: former free-end residual > 1e-9 N*mm
    (-100000, 84, 7224000),  # P1-B: former equilibrium/slope false failure
])
def test_review_minimal_rounding_reproductions(force, position, peak):
    value = checked_one(600, 100, 100, [(force, position)])
    assert value["critical_bending_moment_nmm"] == peak
    assert value["stations"][0]["moment_nmm"] == 0
    assert value["stations"][-1]["moment_nmm"] == 0
    checks = review_engineering_result(value).checks
    assert all(c.passed for c in checks if c.name in (
        "force_equilibrium", "moment_equilibrium") or c.name.endswith("_slope"))


@pytest.mark.parametrize("scale", [1e-200, 1.0, 1e100, 1e200])
def test_rounding_checks_follow_force_and_moment_scales(scale):
    value = checked_one(600, 100, 100, [(-20000 * scale, -100), (-31007 * scale, 84.1)])
    for field in ("reaction_a_n", "reaction_b_n", "critical_bending_moment_nmm"):
        forged = deepcopy(value)
        forged[field] *= 1.01
        assert review_engineering_result(forged).status == "FAIL"


@pytest.mark.parametrize("x", [200.0, 300.0, 400.0])
@pytest.mark.parametrize("force", [1.0, 1e-200, 1e200])
def test_adjacent_opposing_loads_keep_real_moments_and_exact_peak(x, force):
    y = math.nextafter(x, math.inf)
    value = checked_one(600, 100, 100, [(force, x), (-force, y)])
    # Closed-form couple: M(x)=-F*delta*x/L; M(y)=F*delta*(L-y)/L.
    delta = y - x
    stations = {r["position_mm"]: r["moment_nmm"] for r in value["stations"]}
    assert stations[x] == pytest.approx(-force * delta * x / 600, rel=2e-15, abs=0)
    assert stations[y] == pytest.approx(force * delta * (600 - y) / 600, rel=2e-15, abs=0)
    assert len(value["stations"]) == 6
    peak_x = y if x < 300 else x
    assert value["critical_moment_regions"] == [{"x_start_mm": peak_x, "x_end_mm": peak_x}]
    assert value["critical_bending_moment_nmm"] == abs(stations[peak_x])
    # Erasing a tiny but real moment or moving the peak just one ULP is forgery.
    forged = deepcopy(value)
    forged["stations"][2]["moment_nmm"] = 0
    assert review_engineering_result(forged).status == "FAIL"
    forged = deepcopy(value)
    forged["critical_moment_regions"][0] = {"x_start_mm": y if peak_x == x else x,
                                            "x_end_mm": y if peak_x == x else x}
    assert review_engineering_result(forged).status == "FAIL"


def test_strong_cancellation_retains_small_load_and_large_finite_intermediates():
    value = checked_one(600, 100, 100, [(1e300, 200), (1, 200), (-1e300, 200)])
    reference = checked_one(600, 100, 100, [(1, 200)])
    for field in ("total_load_n", "reaction_a_n", "reaction_b_n", "stations", "segments",
                  "critical_bending_moment_nmm", "critical_moment_regions"):
        assert value[field] == reference[field]
    cancelled = checked_one(600, 100, 100, [(1e308, 200), (-1e308, 200)])
    assert cancelled["critical_bending_moment_nmm"] == 0


def test_two_plane_cancellation_and_common_station_reconstruction():
    x = 200.0
    y = math.nextafter(x, math.inf)
    z = math.nextafter(y, math.inf)
    value = checked_two(600, 100, 100, [(1, x), (-1, z)], [(1, y), (-1, z)])
    assert {x, y, z}.issubset(value["common_stations_mm"])
    at_y = next(r for r in value["resultant_stations"] if r["position_mm"] == y)
    # The common station lies inside a narrow plane-1 interval.
    expected_m1 = (y - x) - (z - x) * y / 600
    assert at_y["plane_1_moment_nmm"] == pytest.approx(expected_m1, rel=2e-15, abs=0)
    assert [r["position_mm"] for r in value["critical_stations"]] == [z]
    forged = deepcopy(value)
    forged["resultant_stations"][value["common_stations_mm"].index(y)]["plane_1_moment_nmm"] = 0
    assert review_engineering_result(forged).status == "FAIL"


def test_adjacent_nearly_tied_peaks_are_not_a_plateau():
    x = 300.0
    y = math.nextafter(x, math.inf)
    value = checked_two(600, 100, 100, [(1, x), (-1, y)], [])
    assert [r["position_mm"] for r in value["critical_stations"]] == [x]
    assert value["critical_regions"] == [{"x_start_mm": x, "x_end_mm": x}]


def test_dimensioned_balance_checks_reject_coordinated_forgeries():
    value = checked_one(600, 100, 100, [(-20000, -100), (-100000, 84)])
    force = deepcopy(value)
    force["reaction_a_n"] += 1
    review = review_engineering_result(force)
    assert any(c.name == "force_equilibrium" and not c.passed for c in review.checks)
    moment = deepcopy(value)
    moment["reaction_a_n"] -= 1
    moment["reaction_b_n"] += 1
    review = review_engineering_result(moment)
    assert any(c.name == "moment_equilibrium" and not c.passed for c in review.checks)
    slope = deepcopy(value)
    slope["segments"][1]["shear_n"] += 1
    review = review_engineering_result(slope)
    assert any(c.name == "segment_1_slope" and not c.passed for c in review.checks)
    # Coordinate station and segment edits to preserve continuity; M and slope
    # still have to match the mechanics reconstructed from the original loads.
    moments = deepcopy(value)
    moments["stations"][1]["moment_nmm"] += 1000
    moments["segments"][0]["moment_end_nmm"] += 1000
    moments["segments"][1]["moment_start_nmm"] += 1000
    assert review_engineering_result(moments).status == "FAIL"


@pytest.mark.parametrize("span,left,right,loads", [
    (600, 100, 100, [(1e308, 200), (1e308, 200)]),  # total force
    (1e-300, 1, 0, [(1e308, -1)]),  # reaction
    (600, 100, 100, [(1e308, -100)]),  # moment
])
def test_real_output_overflow_has_explicit_classification(span, left, right, loads):
    with pytest.raises(ValueError, match="calculated force, shear, or moment overflows"):
        one(span, left, right, [PointLoad(*r) for r in loads])


def test_resultant_overflow_with_finite_plane_moments():
    load = [PointLoad(1.4e306, -100)]
    assert math.isfinite(one(600, 100, 100, load).critical_bending_moment_nmm)
    with pytest.raises(ValueError, match="resultant bending moment overflows"):
        two(600, 100, 100, load, load)


def test_reviewer_rejects_unrepresentable_reconstruction():
    value = checked_one(600, 100, 100, [(1, -100)])
    value["loads"][0]["load_n"] = 1e308
    review = review_engineering_result(value)
    assert review.status == "FAIL"
    assert any(c.name == "reconstruction" and not c.passed for c in review.checks)


def test_reviewer_does_not_call_calculator(monkeypatch):
    import mechanical_agent.calculators.shaft_statics_overhung as calculator
    value = checked_one(600, 100, 100, [(1, 200), (-1, math.nextafter(200., math.inf))])

    def forbidden(*args, **kwargs):
        raise AssertionError("Reviewer must independently reconstruct mechanics")

    monkeypatch.setattr(calculator, "calculate_two_support_overhung_signed_point_loads", forbidden)
    monkeypatch.setattr(calculator, "_exact_statics", forbidden)
    monkeypatch.setattr(calculator, "_exact_moment", forbidden)
    assert review_engineering_result(value).status == "PASS"


def test_smallest_subnormal_moment_cannot_be_forged_as_zero():
    smallest = math.nextafter(0., math.inf)
    value = checked_one(600, 100, 100, [(1, 0), (-1, smallest)])
    assert value["critical_bending_moment_nmm"] == smallest
    assert value["critical_moment_regions"] == [{"x_start_mm": smallest, "x_end_mm": smallest}]
    for field in ("critical_bending_moment_nmm", "signed_max_bending_moment_nmm"):
        forged = deepcopy(value)
        forged[field] = 0.
        assert review_engineering_result(forged).status == "FAIL"
    forged = deepcopy(value)
    next(r for r in forged["stations"] if r["position_mm"] == smallest)["moment_nmm"] = 0.
    assert review_engineering_result(forged).status == "FAIL"


@pytest.mark.parametrize("multiple,expected_units", [(1, 1), (2, 1), (3, 2), (4, 3),
                                                       (5, 4), (7, 5), (16, 11)])
@pytest.mark.parametrize("sign", [-1, 1])
def test_two_plane_subnormal_resultant_rounds_only_after_composition(multiple, expected_units, sign):
    smallest = math.nextafter(0.0, math.inf)
    force = sign * multiple * smallest
    value = checked_two(2, 1, 0, [(force, 1)], [(force, 1)])
    at_one = next(r for r in value["resultant_stations"] if r["position_mm"] == 1)
    assert at_one["resultant_bending_moment_nmm"] == expected_units * smallest
    assert value["critical_resultant_bending_moment_nmm"] == expected_units * smallest
    assert [r["position_mm"] for r in value["critical_stations"]] == [1]
    assert value["critical_regions"] == [{"x_start_mm": 1, "x_end_mm": 1}]
    if multiple == 1:
        assert at_one["plane_1_moment_nmm"] == at_one["plane_2_moment_nmm"] == 0


@pytest.mark.parametrize("target", ["station", "peak", "critical", "coordinated"])
def test_reviewer_rejects_underflowed_resultant_forgery(target):
    smallest = math.nextafter(0.0, math.inf)
    value = checked_two(2, 1, 0, [(smallest, 1)], [(smallest, 1)])
    if target in ("station", "coordinated"):
        next(r for r in value["resultant_stations"] if r["position_mm"] == 1)["resultant_bending_moment_nmm"] = 0.0
    if target in ("peak", "coordinated"):
        value["critical_stations"][0]["resultant_bending_moment_nmm"] = 0.0
    if target in ("critical", "coordinated"):
        value["critical_resultant_bending_moment_nmm"] = 0.0
    assert review_engineering_result(value).status == "FAIL"


def test_two_plane_true_underflow_zero_and_halfway_rounding():
    smallest = math.nextafter(0.0, math.inf)
    for p1, p2, expected in [([], [], 0), ([(0, .5)], [(0, .5)], 0),
                              ([(smallest, .5)], [(smallest, .5)], 0),
                              ([(2 * smallest, .5)], [], 0),
                              ([(6 * smallest, .5)], [], 2 * smallest)]:
        value = checked_two(1, 1, 0, p1, p2)
        assert value["critical_resultant_bending_moment_nmm"] == expected
    zero = checked_two(1, 1, 0, [], [])
    zero["critical_resultant_bending_moment_nmm"] = smallest
    assert review_engineering_result(zero).status == "FAIL"


def test_subnormal_adjacent_stations_keep_exact_peak_despite_equal_display():
    smallest = math.nextafter(0.0, math.inf)
    x, y = 1.0, math.nextafter(1.0, math.inf)
    value = checked_two(2, 1, 0, [(smallest, x)], [(smallest, y)])
    assert x in value["common_stations_mm"] and y in value["common_stations_mm"]
    rows = [r for r in value["resultant_stations"] if r["position_mm"] in (x, y)]
    assert len(rows) == 2
    assert all(r["resultant_bending_moment_nmm"] == smallest for r in rows)
    assert [r["position_mm"] for r in value["critical_stations"]] == [x]
    forged = deepcopy(value)
    forged["critical_stations"] = [rows[1]]
    forged["critical_regions"] = [{"x_start_mm": y, "x_end_mm": y}]
    assert review_engineering_result(forged).status == "FAIL"


def test_resultant_unit_conversion_avoids_subnormal_double_rounding():
    smallest = math.nextafter(0.0, math.inf)
    # sqrt((500*s)^2 + (s/2)^2) > 500*s, but rounds to 500*s.
    # In N*m its exact value is above s/2 and therefore rounds to s.
    value = checked_two(2, 1, 0, [(1000 * smallest, 1)], [(smallest, 1)])
    assert value["critical_resultant_bending_moment_nmm"] == 500 * smallest
    assert value["critical_resultant_bending_moment_nm"] == smallest
    forged = deepcopy(value)
    forged["critical_resultant_bending_moment_nm"] = 0.0
    assert review_engineering_result(forged).status == "FAIL"


def test_two_plane_reviewer_does_not_use_calculator_or_rounded_hypot(monkeypatch):
    import mechanical_agent.calculators.shaft_statics_overhung_two_plane as calculator
    smallest = math.nextafter(0.0, math.inf)
    value = checked_two(2, 1, 0, [(smallest, 1)], [(smallest, 1)])

    def forbidden(*args, **kwargs):
        raise AssertionError("Reviewer must reconstruct from raw loads independently")

    monkeypatch.setattr(calculator, "_rounded_sqrt", forbidden)
    monkeypatch.setattr(calculator, "_exact_statics", forbidden)
    monkeypatch.setattr(calculator, "_exact_moment", forbidden)
    monkeypatch.setattr(math, "hypot", forbidden)
    assert review_engineering_result(value).status == "PASS"


def test_exact_resultant_rounding_at_binary64_boundaries():
    from fractions import Fraction
    from mechanical_agent.calculators.shaft_statics_overhung_two_plane import _rounded_sqrt
    from mechanical_agent.review.overhung_statics import reconstructed_magnitude

    smallest = math.nextafter(0.0, math.inf)
    largest = float.fromhex("0x1.fffffffffffffp+1023")
    # Subnormal, normal/subnormal transition, binade changes and top finite binade.
    for lower in (0.0, smallest, 2 * smallest,
                  math.nextafter(float.fromhex("0x1p-1022"), 0.0),
                  1.0, math.nextafter(2.0, 0.0), math.nextafter(largest, 0.0)):
        upper = math.nextafter(lower, math.inf)
        midpoint = (Fraction(lower) + Fraction(upper)) / 2
        gap = Fraction(upper) - Fraction(lower)
        even_lower = (Fraction(lower) / Fraction(math.ulp(lower))).numerator % 2 == 0
        for root, expected in ((midpoint - gap / 16, lower),
                               (midpoint, lower if even_lower else upper),
                               (midpoint + gap / 16, upper)):
            for round_root in (_rounded_sqrt, reconstructed_magnitude):
                assert round_root(root * root) == expected
    overflow_midpoint = Fraction(largest) + Fraction(math.ulp(largest)) / 2
    for round_root in (_rounded_sqrt, reconstructed_magnitude):
        assert round_root((overflow_midpoint - Fraction(math.ulp(largest)) / 16) ** 2) == largest
        with pytest.raises(ValueError, match="resultant bending moment overflows"):
            round_root(overflow_midpoint ** 2)


_ROUNDING_MAGNITUDES = [math.nextafter(0.0, math.inf), float.fromhex("0x1p-1022"),
                        math.nextafter(1.0, 0.0), 1.0, math.nextafter(1.0, math.inf), 2.0]


@pytest.mark.parametrize("magnitude", _ROUNDING_MAGNITUDES)
@pytest.mark.parametrize("direction", [-math.inf, math.inf])
@pytest.mark.parametrize("target", ["critical", "converted", "station_resultant", "peak_resultant",
                                    "station_component", "peak_component", "other_component"])
def test_two_plane_rejects_adjacent_output_forgery(magnitude, direction, target):
    value = checked_two(2, 1, 0, [(2 * magnitude, 1)], [])
    station = next(r for r in value["resultant_stations"] if r["position_mm"] == 1)
    peak = value["critical_stations"][0]
    mapping = {
        "critical": (value, "critical_resultant_bending_moment_nmm"),
        "converted": (value, "critical_resultant_bending_moment_nm"),
        "station_resultant": (station, "resultant_bending_moment_nmm"),
        "peak_resultant": (peak, "resultant_bending_moment_nmm"),
        "station_component": (station, "plane_1_moment_nmm"),
        "peak_component": (peak, "plane_1_moment_nmm"),
        "other_component": (station, "plane_2_moment_nmm"),
    }
    row, field = mapping[target]
    original = row[field]
    row[field] = math.nextafter(original, direction)
    assert row[field] != original
    assert review_engineering_result(value).status == "FAIL"


@pytest.mark.parametrize("magnitude", _ROUNDING_MAGNITUDES)
@pytest.mark.parametrize("direction", [-math.inf, math.inf])
@pytest.mark.parametrize("target", ["total", "reaction_a", "reaction_b", "station", "start", "end",
                                    "shear", "maximum", "minimum", "critical", "converted"])
def test_one_plane_rejects_adjacent_output_forgery(magnitude, direction, target):
    value = checked_one(1, 1, 0, [(4 * magnitude, .5)])
    station = next(r for r in value["stations"] if r["position_mm"] == .5)
    before = next(r for r in value["segments"] if r["x_end_mm"] == .5)
    after = next(r for r in value["segments"] if r["x_start_mm"] == .5)
    mapping = {
        "total": (value, "total_load_n"),
        "reaction_a": (value, "reaction_a_n"),
        "reaction_b": (value, "reaction_b_n"),
        "station": (station, "moment_nmm"),
        "start": (after, "moment_start_nmm"),
        "end": (before, "moment_end_nmm"),
        "shear": (before, "shear_n"),
        "maximum": (value, "signed_max_bending_moment_nmm"),
        "minimum": (value, "signed_min_bending_moment_nmm"),
        "critical": (value, "critical_bending_moment_nmm"),
        "converted": (value, "critical_bending_moment_nm"),
    }
    row, field = mapping[target]
    original = row[field]
    row[field] = math.nextafter(original, direction)
    assert row[field] != original
    assert review_engineering_result(value).status == "FAIL"


@pytest.mark.parametrize("multiple", [2, 6])
@pytest.mark.parametrize("sign", [-1, 1])
def test_midpoint_coordinated_wrong_even_rounding_is_rejected(multiple, sign):
    smallest = math.nextafter(0.0, math.inf)
    value = checked_one(1, 1, 0, [(sign * multiple * smallest, .5)])
    station = next(r for r in value["stations"] if r["position_mm"] == .5)
    correct = -sign * (0.0 if multiple == 2 else 2 * smallest)
    assert station["moment_nmm"] == correct
    assert math.copysign(1.0, station["moment_nmm"]) == -sign
    wrong = -sign * smallest
    station["moment_nmm"] = wrong
    for segment in value["segments"]:
        if segment["x_start_mm"] == .5:
            segment["moment_start_nmm"] = wrong
        if segment["x_end_mm"] == .5:
            segment["moment_end_nmm"] = wrong
    value["signed_min_bending_moment_nmm" if sign == 1 else "signed_max_bending_moment_nmm"] = wrong
    value["critical_bending_moment_nmm"] = smallest
    review = review_engineering_result(value)
    assert review.status == "FAIL"
    failed = {c.name for c in review.checks if not c.passed}
    assert {"station_2", "segment_1_moments", "segment_2_moments", "signed_extrema", "critical"} <= failed
    # Physical integrated bounds remain separate; these midpoint edits fit them.
    assert all(c.passed for c in review.checks if c.name.endswith("_slope"))


@pytest.mark.parametrize("force", [0.0, 2 * math.nextafter(0.0, math.inf),
                                   -2 * math.nextafter(0.0, math.inf)])
def test_zero_sign_matches_independently_rounded_moment(force):
    value = checked_one(1, 1, 0, [(force, .5)])
    station = next(r for r in value["stations"] if r["position_mm"] == .5)
    assert station["moment_nmm"] == 0.0
    assert math.copysign(1.0, station["moment_nmm"]) == (-1.0 if force > 0 else 1.0)
    station["moment_nmm"] = math.copysign(0.0, -math.copysign(1.0, station["moment_nmm"]))
    assert review_engineering_result(value).status == "FAIL"


def test_resultant_zero_sign_and_rounded_comparison_contract():
    from fractions import Fraction
    from mechanical_agent.review.overhung_statics import correctly_rounded

    smallest = math.nextafter(0.0, math.inf)
    assert correctly_rounded(0, Fraction(0))
    assert correctly_rounded(1, Fraction(1))
    assert not correctly_rounded(True, Fraction(1))
    assert not correctly_rounded(float("nan"), Fraction(1))
    assert not correctly_rounded(float("inf"), Fraction(1))
    assert not correctly_rounded(0.0, -Fraction(smallest) / 2)
    assert correctly_rounded(-0.0, -Fraction(smallest) / 2)
    for lower in (0.0, smallest, 2 * smallest,
                  math.nextafter(float.fromhex("0x1p-1022"), 0.0),
                  math.nextafter(1.0, 0.0), 1.0, math.nextafter(2.0, 0.0), 2.0):
        upper = math.nextafter(lower, math.inf)
        midpoint = (Fraction(lower) + Fraction(upper)) / 2
        even = (Fraction(lower) / Fraction(math.ulp(lower))).numerator % 2 == 0
        for sign in (-1, 1):
            correct = sign * (lower if even else upper)
            wrong = sign * (upper if even else lower)
            assert correctly_rounded(correct, sign * midpoint)
            assert not correctly_rounded(wrong, sign * midpoint)
    value = checked_two(2, 1, 0, [], [])
    value["critical_resultant_bending_moment_nmm"] = -0.0
    assert review_engineering_result(value).status == "FAIL"


def test_rounding_review_independence_with_calculator_entrypoints_disabled(monkeypatch):
    import mechanical_agent.calculators.shaft_statics_overhung as single
    import mechanical_agent.calculators.shaft_statics_overhung_two_plane as double
    smallest = math.nextafter(0.0, math.inf)
    one_value = checked_one(1, 1, 0, [(2 * smallest, .5)])
    two_value = checked_two(2, 1, 0, [(2, 1)], [])

    def forbidden(*args, **kwargs):
        raise AssertionError("Reviewer called a Calculator function")

    for module, names in ((single, ("calculate_two_support_overhung_signed_point_loads",
                                   "_exact_statics", "_exact_moment", "_rounded")),
                          (double, ("calculate_two_support_overhung_two_plane_point_loads",
                                    "_exact_statics", "_exact_moment", "_rounded", "_rounded_sqrt"))):
        for name in names:
            monkeypatch.setattr(module, name, forbidden)
    assert review_engineering_result(one_value).status == "PASS"
    assert review_engineering_result(two_value).status == "PASS"
    two_value["critical_resultant_bending_moment_nmm"] = math.nextafter(1.0, 0.0)
    assert review_engineering_result(two_value).status == "FAIL"
