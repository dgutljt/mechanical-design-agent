"""Independent reconstruction of one- and two-plane overhung point-load statics."""

import math
from fractions import Fraction
from decimal import Decimal, localcontext

ONE = "two_support_overhung_signed_point_load_v1"
CONVENTION = (
    "+x A-to-B; +q is the chosen transverse direction; forces/reactions positive +q; "
    "V=sum(left external forces); dM/dx=V; plane 1 +q=+y gives M_z=M; "
    "plane 2 +q=+z gives M_y=-M"
)
TWO_CONVENTION = (
    "+x A-to-B; plane_1 loads along +y, plane_2 loads along +z; "
    "plane_1_moment is M_z, plane_2_moment is -M_y; each signed "
    "scalar follows dM/dx=V on shaft domain [-a,L+b]"
)
UNITS = {"force": "N", "position": "mm", "moment": "N*mm", "converted_moment": "N*m"}


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def correctly_rounded(actual, expected):
    """Match the independently determined binary64 value, including zero sign.

    Fraction-to-float uses nearest, ties-to-even; irrational resultants arrive
    already certified by reconstructed_magnitude's exact midpoint tests.
    Exact zero is +0; a negative value rounded to zero is -0. Integer JSON
    numbers are accepted only when exactly equal to that binary64 value.
    Physical residual bounds are checked separately with balanced/rounding.
    """
    if not finite(actual):
        return False
    try:
        rounded_expected = float(expected)
    except (ValueError, OverflowError):
        return False
    if not math.isfinite(rounded_expected) or actual != rounded_expected:
        return False
    return (rounded_expected != 0.0
            or math.copysign(1.0, actual) == math.copysign(1.0, rounded_expected))


def rounding(value):
    """Maximum final round-to-nearest error, in the quantity's own units."""
    return Fraction(math.ulp(float(value))) / 2


def balanced(residual, bound):
    return abs(residual) <= bound


def exact_reconstruction(loads, span):
    # Independent right-section construction: no Calculator imports or calls.
    terms = [(Fraction(r["load_n"]), Fraction(r["position_mm"])) for r in loads]
    length = Fraction(span)
    total = sum((f for f, _ in terms), Fraction())
    ra = sum((f * (p - length) for f, p in terms), Fraction()) / length
    rb = -sum((f * p for f, p in terms), Fraction()) / length

    def moment(position):
        x = Fraction(position)
        return (sum((f * (p - x) for f, p in terms if p >= x), Fraction())
                + (ra * -x if x <= 0 else 0)
                + (rb * (length - x) if x <= length else 0))

    def shear(position):
        x = Fraction(position)
        return -(sum((f for f, p in terms if p > x), Fraction())
                 + (ra if x < 0 else 0) + (rb if x < length else 0))

    return total, ra, rb, moment, shear


def records(data, key, fields, nonempty=False):
    items = data.get(key)
    return (isinstance(items, list) and (not nonempty or bool(items))
            and all(isinstance(item, dict) and set(item) == set(fields)
                    and all(finite(item[field]) for field in fields) for item in items))


def reconstruct(data, review, prefix=""):
    def check(name, valid, message):
        review.add(prefix + name, valid, message)

    geometry = [data.get(key) for key in (
        "support_span_mm", "left_overhang_mm", "right_overhang_mm")]
    valid = (all(finite(v) for v in geometry) and geometry[0] > 0
             and geometry[1] >= 0 and geometry[2] >= 0
             and (geometry[1] > 0 or geometry[2] > 0))
    if valid:
        span, left, right = geometry
        end = span + right
        valid = math.isfinite(end) and math.isfinite(left + end)
    check("geometry", valid, "invalid or overflowing support/overhang geometry")
    if not valid:
        return None
    shapes = {
        "loads": ({"load_n", "position_mm"}, False),
        "stations": ({"position_mm", "moment_nmm"}, True),
        "segments": ({"x_start_mm", "x_end_mm", "shear_n",
                      "moment_start_nmm", "moment_end_nmm"}, True),
        "critical_moment_regions": ({"x_start_mm", "x_end_mm"}, True),
    }
    for name, (fields, nonempty) in shapes.items():
        valid = records(data, name, fields, nonempty)
        check(name + "_structure", valid, name + " must contain finite complete records")
        if not valid:
            return None
    check("model_id", data.get("model_id") == ONE, "wrong overhung plane model ID")
    check("units", data.get("units") == UNITS, "overhung units mismatch")
    check("sign_convention", data.get("sign_convention") == CONVENTION,
          "overhung sign convention mismatch")
    loads = data["loads"]
    valid = all(-left <= item["position_mm"] <= end for item in loads)
    check("load_domain", valid, "load outside shaft domain")
    check("load_order", all(a["position_mm"] <= b["position_mm"]
                            for a, b in zip(loads, loads[1:])), "loads not sorted")
    if not valid:
        return None
    try:
        total, ra, rb, moment, shear = exact_reconstruction(loads, span)
        events = sorted({-left, 0.0, span, end,
                         *(item["position_mm"] for item in loads)})
        moments = [moment(x) for x in events]
        shears = [shear(x) for x in events[:-1]]
        critical = max(abs(max(moments)), abs(min(moments)))
        # Conversion checks only final representability, not large cancelling
        # intermediate products which never need to be represented as floats.
        if not all(math.isfinite(float(v)) for v in (total, ra, rb, *moments, *shears, critical)):
            raise ValueError("nonfinite reconstructed mechanics")
    except (ValueError, OverflowError) as exc:
        check("reconstruction", False, str(exc))
        return None
    valid_reactions = all(finite(data.get(k)) for k in ("reaction_a_n", "reaction_b_n"))
    check("reaction_structure", valid_reactions, "reactions must be finite numbers")
    if not valid_reactions:
        return None
    reported_a, reported_b = Fraction(data["reaction_a_n"]), Fraction(data["reaction_b_n"])
    check("total_load", correctly_rounded(data.get("total_load_n"), total), "total load mismatch")
    # Force bound [N]: only the two reported reactions were rounded.
    check("force_equilibrium", balanced(reported_a + reported_b + total,
          rounding(ra) + rounding(rb)), "force equilibrium failed")
    # Moment bound [N*mm]: RB rounding times the exact lever arm. Input
    # products and the residual are evaluated exactly, so add no float floor.
    load_moment = sum((Fraction(r["load_n"]) * Fraction(r["position_mm"])
                       for r in loads), Fraction())
    check("moment_equilibrium", balanced(reported_b * Fraction(span) + load_moment,
          rounding(rb) * Fraction(span)), "moment equilibrium about A failed")
    check("reactions", correctly_rounded(data["reaction_a_n"], ra)
          and correctly_rounded(data["reaction_b_n"], rb), "signed reactions mismatch")
    stations, segments = data["stations"], data["segments"]
    check("event_count", len(stations) == len(events)
          and len(segments) == len(events) - 1, "event/segment count mismatch")
    for i, (x, expected_moment) in enumerate(zip(events, moments)):
        if i < len(stations):
            check(f"station_{i}", stations[i]["position_mm"] == x
                  and correctly_rounded(stations[i]["moment_nmm"], expected_moment),
                  "event station or bending moment mismatch")
    check("free_end_moments", moments[0] == 0 and moments[-1] == 0
          and len(stations) == len(events)
          and correctly_rounded(stations[0]["moment_nmm"], 0)
          and correctly_rounded(stations[-1]["moment_nmm"], 0),
          "free-end moment must be zero without applied couples")
    for i, (start, stop) in enumerate(zip(events, events[1:])):
        if i >= len(segments):
            break
        segment = segments[i]
        check(f"segment_{i}_bounds", segment["x_start_mm"] == start
              and segment["x_end_mm"] == stop, "segment event bounds mismatch")
        check(f"segment_{i}_shear", correctly_rounded(segment["shear_n"], shears[i]),
              "segment shear or event jump mismatch")
        check(f"segment_{i}_moments", correctly_rounded(segment["moment_start_nmm"], moments[i])
              and correctly_rounded(segment["moment_end_nmm"], moments[i + 1]),
              "segment bending moment mismatch")
        # Slope in integrated form [N*mm]. Endpoint subtraction can
        # cancel; bound the rounding of both M values and V*exact dx separately.
        dx = Fraction(stop) - Fraction(start)
        residual = (Fraction(segment["moment_end_nmm"])
                    - Fraction(segment["moment_start_nmm"])
                    - Fraction(segment["shear_n"]) * dx)
        check(f"segment_{i}_slope", balanced(residual,
              rounding(moments[i]) + rounding(moments[i + 1]) + rounding(shears[i]) * dx),
              "segment dM/dx=V failed")
        if i:
            jump = shears[i] - shears[i - 1]
            jump_residual = (Fraction(segment["shear_n"])
                             - Fraction(segments[i - 1]["shear_n"]) - jump)
            check(f"segment_{i}_jump", balanced(jump_residual,
                  rounding(shears[i]) + rounding(shears[i - 1])), "shear jump mismatch")
            check(f"segment_{i}_continuity", correctly_rounded(segments[i - 1]["moment_end_nmm"],
                  segment["moment_start_nmm"]), "moment discontinuity")
    check("signed_extrema", correctly_rounded(data.get("signed_max_bending_moment_nmm"), max(moments))
          and correctly_rounded(data.get("signed_min_bending_moment_nmm"), min(moments)),
          "signed extrema mismatch")
    check("critical", correctly_rounded(data.get("critical_bending_moment_nmm"), critical)
          and correctly_rounded(data.get("critical_bending_moment_nm"), critical / 1000),
          "critical magnitude or units mismatch")
    expected_regions = []
    for i, (x, m) in enumerate(zip(events, moments)):
        if abs(m) != critical:
            continue
        stop = x
        if (i < len(shears) and shears[i] == 0
                and abs(moments[i + 1]) == critical):
            stop = events[i + 1]
        if expected_regions and expected_regions[-1][1] == x:
            expected_regions[-1] = (expected_regions[-1][0], stop)
        else:
            expected_regions.append((x, stop))
    regions = data["critical_moment_regions"]
    check("critical_regions", len(regions) == len(expected_regions)
          and all(r["x_start_mm"] == a and r["x_end_mm"] == b
                  for r, (a, b) in zip(regions, expected_regions)),
          "critical ties or true plateaus mismatch")
    return events, moments, loads


def verify_one(data, review):
    reconstruct(data, review)



def reconstructed_magnitude(square):
    """Independently certify the nearest binary64 root by exact midpoint squares."""
    if square == 0:
        return 0.0
    # Decimal supplies only a candidate; rational boundary checks decide rounding.
    with localcontext() as context:
        context.prec = 80
        candidate = float((Decimal(square.numerator) / Decimal(square.denominator)).sqrt())
    largest = float.fromhex("0x1.fffffffffffffp+1023")
    overflow_midpoint = Fraction(largest) + Fraction(math.ulp(largest)) / 2
    if square >= overflow_midpoint ** 2:
        raise ValueError("resultant bending moment overflows")
    if not math.isfinite(candidate):
        candidate = largest
    while True:
        center = Fraction(candidate)
        even = (center / Fraction(math.ulp(candidate))).numerator % 2 == 0
        if candidate > 0:
            previous = math.nextafter(candidate, 0.0)
            lower = (Fraction(previous) + center) / 2
            if square < lower ** 2 or (square == lower ** 2 and not even):
                candidate = previous
                continue
        following = math.nextafter(candidate, math.inf)
        upper = ((center + Fraction(following)) / 2
                 if math.isfinite(following) else overflow_midpoint)
        if square > upper ** 2 or (square == upper ** 2 and not even):
            candidate = following
            continue
        return candidate


def verify_two(data, review):
    review.add("coordinate_convention", data.get("coordinate_convention") == TWO_CONVENTION,
               "two-plane coordinate convention mismatch")
    review.add("units", data.get("units") == UNITS, "two-plane units mismatch")
    planes = []
    for name in ("plane_1", "plane_2"):
        plane = data.get(name)
        valid = isinstance(plane, dict) and plane.get("model_id") == ONE
        review.add(name + "_model", valid, "nested plane model mismatch")
        if not valid:
            return
        before = review.status
        reconstructed = reconstruct(plane, review, name + "_")
        if reconstructed is None or (before == "PASS" and review.status != "PASS"):
            return
        review.add(name + "_geometry", all(plane.get(k) == data.get(k) for k in (
            "support_span_mm", "left_overhang_mm", "right_overhang_mm")),
            "nested plane geometry mismatch")
        planes.append(reconstructed)
    if review.status != "PASS":
        return
    common = sorted({*(x for events, _, _ in planes for x in events)})
    reported_common = data.get("common_stations_mm")
    valid = isinstance(reported_common, list) and reported_common == common
    review.add("common_stations", valid, "common station union mismatch")
    if not valid:
        return

    span = data["support_span_mm"]
    reconstructions = [exact_reconstruction(plane[2], span) for plane in planes]
    exact_expected = [(x, reconstructions[0][3](x), reconstructions[1][3](x)) for x in common]
    squared = [m1 * m1 + m2 * m2 for _, m1, m2 in exact_expected]
    try:
        expected = [(x, float(m1), float(m2), reconstructed_magnitude(square))
                    for (x, m1, m2), square in zip(exact_expected, squared)]
        critical_nm = reconstructed_magnitude(max(squared) / 1000000)
    except (ValueError, OverflowError):
        review.add("resultant_reconstruction", False, "resultant bending moment overflows")
        return
    fields = {"position_mm", "plane_1_moment_nmm", "plane_2_moment_nmm",
              "resultant_bending_moment_nmm"}
    for key in ("resultant_stations", "critical_stations"):
        valid = records(data, key, fields, True)
        review.add(key + "_structure", valid, key + " structure mismatch")
        if not valid:
            return
    reported = data["resultant_stations"]
    review.add("resultant_count", len(reported) == len(expected),
               "resultant station count mismatch")
    for i, (x, m1, m2, magnitude) in enumerate(expected[:len(reported)]):
        row = reported[i]
        review.add(f"resultant_{i}", row["position_mm"] == x
                   and correctly_rounded(row["plane_1_moment_nmm"], m1)
                   and correctly_rounded(row["plane_2_moment_nmm"], m2)
                   and correctly_rounded(row["resultant_bending_moment_nmm"], magnitude),
                   "same-station component/resultant mismatch")
    critical = max(row[3] for row in expected)
    review.add("critical_value", correctly_rounded(data.get("critical_resultant_bending_moment_nmm"), critical)
               and correctly_rounded(data.get("critical_resultant_bending_moment_nm"), critical_nm),
               "critical resultant or conversion mismatch")
    peak_squared = max(squared)
    peaks = [row for row, square in zip(expected, squared) if square == peak_squared]
    reported_peaks = data["critical_stations"]
    valid = len(reported_peaks) == len(peaks)
    for row, (x, m1, m2, magnitude) in zip(reported_peaks, peaks):
        valid = valid and row["position_mm"] == x and all((
            correctly_rounded(row["plane_1_moment_nmm"], m1),
            correctly_rounded(row["plane_2_moment_nmm"], m2),
            correctly_rounded(row["resultant_bending_moment_nmm"], magnitude)))
    review.add("critical_stations", valid, "critical ties or components mismatch")
    regions = []
    for i, row in enumerate(expected):
        if row not in peaks:
            continue
        stop = row[0]
        if i + 1 < len(expected) and expected[i + 1] in peaks:
            if (reconstructions[0][4](row[0]) == 0
                    and reconstructions[1][4](row[0]) == 0):
                stop = expected[i + 1][0]
        if regions and regions[-1][1] == row[0]:
            regions[-1] = (regions[-1][0], stop)
        else:
            regions.append((row[0], stop))
    valid = records(data, "critical_regions", {"x_start_mm", "x_end_mm"}, True)
    if valid:
        reported_regions = data["critical_regions"]
        valid = len(reported_regions) == len(regions) and all(
            r["x_start_mm"] == start and r["x_end_mm"] == stop
            for r, (start, stop) in zip(reported_regions, regions))
    review.add("critical_regions", valid, "critical regions or plateau mismatch")
