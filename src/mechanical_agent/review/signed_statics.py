"""Independent deterministic checks for signed single-plane point-load output."""
import math

REL_TOL = 1e-12

def close(a, b, absolute=1e-9):
    return math.isfinite(b) and math.isclose(a, b, rel_tol=REL_TOL, abs_tol=absolute)

def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

def verify(data, review):
    # Fixed verifier contract; never import numerical or schema truth from Calculator.
    sign_convention = "x A-to-B; +q is chosen transverse direction (vertical plane: upward); forces/reactions positive +q; V=sum(left external forces); dM/dx=V; +M follows this derivative (vertical plane: sagging)"
    units = {"force": "N", "position": "mm", "moment": "N*mm", "converted_moment": "N*m"}

    nested = {
        "loads": ("load_n", "position_mm"),
        "stations": ("position_mm", "moment_nmm"),
        "segments": ("x_start_mm", "x_end_mm", "shear_n", "moment_start_nmm", "moment_end_nmm"),
        "critical_moment_regions": ("x_start_mm", "x_end_mm"),
    }
    for name, fields in nested.items():
        value = data.get(name)
        valid = (isinstance(value, list) and (name == "loads" or bool(value))
                 and all(isinstance(item, dict) and set(item) == set(fields)
                         and all(finite(item[field]) for field in fields)
                         for item in value))
        review.add(f"{name}_structure", valid, f"{name} must contain finite numeric records")
        if not valid:
            return
    review.add("units", data.get("units") == units, "signed statics units mismatch")
    review.add("sign_convention", data["sign_convention"] == sign_convention,
               "signed statics sign convention mismatch")
    span, loads = data["span_mm"], data["loads"]
    valid = span > 0 and all(0 <= load["position_mm"] <= span for load in loads)
    review.add("input_ranges", valid, "span must be positive and loads within supports")
    if not valid:
        return
    review.add("load_order", all(a["position_mm"] <= b["position_mm"]
                                 for a, b in zip(loads, loads[1:])), "loads not sorted")
    total = math.fsum(load["load_n"] for load in loads)
    left, right = data["reaction_a_n"], data["reaction_b_n"]
    expected_right = -math.fsum(load["load_n"] * (load["position_mm"] / span)
                                for load in loads)
    expected_left = -total - expected_right
    review.add("total_load", close(data["total_load_n"], total), "total load mismatch")
    review.add("force_equilibrium", close(math.fsum((left, right, total)), 0),
               "signed force equilibrium failed")
    review.add("moment_equilibrium", close(math.fsum(
        [right * span] + [load["load_n"] * load["position_mm"] for load in loads]), 0),
        "signed moment equilibrium failed")
    review.add("reaction_values", close(left, expected_left) and close(right, expected_right),
               "support reactions mismatch signed equilibrium")

    events = sorted({0.0, span, *(load["position_mm"] for load in loads)})
    stations, segments = data["stations"], data["segments"]
    review.add("event_count", len(stations) == len(events) and len(segments) == len(events)-1,
               "station or segment count mismatch")

    def moment_at(x):
        return math.fsum([left*x] + [
            load["load_n"] * (x-load["position_mm"])
            for load in loads if load["position_mm"] <= x])

    moments = [moment_at(x) for x in events]
    for i, x in enumerate(events):
        if i >= len(stations):
            break
        review.add(f"station_{i}", close(stations[i]["position_mm"], x)
                   and close(stations[i]["moment_nmm"], moments[i]),
                   "station position or signed moment mismatch")
    if len(stations) == len(events):
        review.add("support_moments", close(moments[0], 0) and close(moments[-1], 0)
                   and close(stations[0]["moment_nmm"], 0)
                   and close(stations[-1]["moment_nmm"], 0),
                   "support moment must be zero")
    for i, (start, end) in enumerate(zip(events, events[1:])):
        if i >= len(segments):
            break
        segment = segments[i]
        shear = math.fsum([left] + [load["load_n"] for load in loads
                                    if load["position_mm"] <= start])
        review.add(f"segment_{i}_bounds", close(segment["x_start_mm"], start)
                   and close(segment["x_end_mm"], end), "segment event bounds mismatch")
        review.add(f"segment_{i}_shear", close(segment["shear_n"], shear),
                   "piecewise constant shear or event jump mismatch")
        review.add(f"segment_{i}_moments",
                   close(segment["moment_start_nmm"], moments[i])
                   and close(segment["moment_end_nmm"], moments[i+1]),
                   "segment moment mismatch")
        review.add(f"segment_{i}_slope", close(
            segment["moment_end_nmm"] - segment["moment_start_nmm"],
            segment["shear_n"] * (end-start)), "dM/dx = V failed")
        if i:
            review.add(f"segment_{i}_continuity", close(
                segments[i-1]["moment_end_nmm"], segment["moment_start_nmm"]),
                "moment discontinuity at point force")
            jump = math.fsum(load["load_n"] for load in loads
                             if load["position_mm"] == start)
            review.add(f"segment_{i}_jump", close(
                segment["shear_n"] - segments[i-1]["shear_n"], jump),
                "shear jump mismatch at coincident loads")
    maximum, minimum = max(moments), min(moments)
    critical = max(abs(maximum), abs(minimum))
    review.add("signed_extrema", close(data["signed_max_bending_moment_nmm"], maximum)
               and close(data["signed_min_bending_moment_nmm"], minimum),
               "signed maximum or minimum mismatch")
    review.add("critical_magnitude", close(data["critical_bending_moment_nmm"], critical)
               and close(data["critical_bending_moment_nm"], critical/1000),
               "critical absolute bending magnitude mismatch")

    def peak(value):
        return math.isclose(abs(value), critical, rel_tol=REL_TOL, abs_tol=0)

    expected = []
    for i, (position, moment) in enumerate(zip(events, moments)):
        if not peak(moment):
            continue
        end = position
        if i < len(events)-1 and peak(moments[i+1]):
            shear = math.fsum([left] + [load["load_n"] for load in loads
                                        if load["position_mm"] <= position])
            if close(shear, 0, 1e-12):
                end = events[i+1]
        if expected and expected[-1][1] == position:
            expected[-1] = (expected[-1][0], end)
        else:
            expected.append((position, end))
    regions = data["critical_moment_regions"]
    valid_regions = len(regions) == len(expected)
    for i, region in enumerate(regions):
        start, end = region["x_start_mm"], region["x_end_mm"]
        valid_regions = valid_regions and 0 <= start <= end <= span
        if i:
            valid_regions = valid_regions and regions[i-1]["x_end_mm"] < start
        if i < len(expected):
            valid_regions = valid_regions and close(start, expected[i][0]) and close(end, expected[i][1])
    review.add("critical_regions", valid_regions, "critical tie or plateau regions mismatch")
    if not loads:
        review.add("zero_load", left == right == total == maximum == minimum == critical == 0
                   and expected == [(0.0, span)] and all(s["shear_n"] == 0 for s in segments),
                   "empty load plane must be identically zero over full span")
