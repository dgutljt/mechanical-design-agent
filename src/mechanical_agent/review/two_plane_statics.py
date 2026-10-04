"""Independent checks of reviewed signed planes and their same-station resultants."""
import math

MODEL_ID = "simply_supported_signed_multi_point_load_v1"
CONVENTION = (
    "+x A-to-B; plane_1 loads along +y, plane_2 loads along +z; "
    "plane_1_moment is M_z, plane_2_moment is -M_y; each signed "
    "scalar follows the signed one-plane dM/dx=V convention"
)
UNITS = {"force": "N", "position": "mm", "moment": "N*mm", "converted_moment": "N*m"}
STATION_FIELDS = {"position_mm", "plane_1_moment_nmm", "plane_2_moment_nmm",
                  "resultant_bending_moment_nmm"}


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _close(a, b):
    return math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-9)


def _moment_at(plane, x):
    for station in plane["stations"]:
        if station["position_mm"] == x:
            return station["moment_nmm"]
    for segment in plane["segments"]:
        if segment["x_start_mm"] < x < segment["x_end_mm"]:
            return math.fsum((segment["moment_start_nmm"],
                              segment["shear_n"] * (x - segment["x_start_mm"])))
    raise ValueError("common station outside signed plane segments")


def verify(data, review):
    # Import locally to avoid the dispatch module's import cycle.
    from mechanical_agent.review.engineering_result import review_engineering_result

    review.add("coordinate_convention", data.get("coordinate_convention") == CONVENTION,
               "two-plane coordinate/component convention mismatch")
    review.add("units", data.get("units") == UNITS, "two-plane units mismatch")
    planes = []
    for name in ("plane_1", "plane_2"):
        plane = data.get(name)
        valid = isinstance(plane, dict) and plane.get("model_id") == MODEL_ID
        review.add(f"{name}_model", valid, f"{name} must contain the signed one-plane model")
        if not valid:
            return
        nested = review_engineering_result(plane)
        review.add(f"{name}_review", nested.status == "PASS",
                   f"{name} signed statics Reviewer failed: {nested.errors}")
        if nested.status != "PASS":
            return
        planes.append(plane)
    span = data["span_mm"]
    review.add("same_span", all(p["span_mm"] == span for p in planes),
               "both signed planes must use the outer span")
    if not all(p["span_mm"] == span for p in planes):
        return
    common = sorted({0.0, span, *(s["position_mm"] for p in planes for s in p["stations"])})
    reported_common = data.get("common_stations_mm")
    valid_common = (isinstance(reported_common, list)
                    and all(_finite(x) for x in reported_common)
                    and reported_common == common)
    review.add("common_stations", valid_common,
               "common stations must be the sorted unique union of both event sets")
    if not valid_common:
        return
    reported = data.get("resultant_stations")
    valid = (isinstance(reported, list) and len(reported) == len(common)
             and all(isinstance(s, dict) and set(s) == STATION_FIELDS
                     and all(_finite(s[field]) for field in STATION_FIELDS) for s in reported))
    review.add("resultant_station_structure", valid,
               "resultant stations must have finite complete component records")
    if not valid:
        return
    expected = []
    for i, x in enumerate(common):
        m1, m2 = _moment_at(planes[0], x), _moment_at(planes[1], x)
        magnitude = math.hypot(m1, m2)
        if not math.isfinite(magnitude):
            review.add("finite_resultant", False, "resultant overflow")
            return
        expected.append((x, m1, m2, magnitude))
        station = reported[i]
        review.add(f"station_{i}_position", station["position_mm"] == x,
                   "resultant station position mismatch")
        review.add(f"station_{i}_components",
                   _close(station["plane_1_moment_nmm"], m1)
                   and _close(station["plane_2_moment_nmm"], m2),
                   "same-station bending components mismatch")
        review.add(f"station_{i}_resultant", _close(station["resultant_bending_moment_nmm"], magnitude),
                   "same-station resultant mismatch")
    critical = max(row[3] for row in expected)
    review.add("critical_value", _close(data["critical_resultant_bending_moment_nmm"], critical)
               and _close(data["critical_resultant_bending_moment_nm"], critical / 1000),
               "critical resultant value or conversion mismatch")
    peaks = [row for row in expected if math.isclose(row[3], critical, rel_tol=1e-12, abs_tol=0)]
    critical_stations = data.get("critical_stations")
    valid_peaks = (isinstance(critical_stations, list) and len(critical_stations) == len(peaks)
                   and all(isinstance(s, dict) and set(s) == STATION_FIELDS
                           and all(_finite(s[field]) for field in STATION_FIELDS)
                           for s in critical_stations))
    if valid_peaks:
        for station, row in zip(critical_stations, peaks):
            valid_peaks = valid_peaks and station["position_mm"] == row[0]
            valid_peaks = valid_peaks and all(_close(station[field], value) for field, value in zip(
                ("plane_1_moment_nmm", "plane_2_moment_nmm", "resultant_bending_moment_nmm"), row[1:]))
    review.add("critical_stations", valid_peaks,
               "all critical stations and their components must be retained")
    regions = []
    for i, row in enumerate(expected):
        if row not in peaks:
            continue
        end = row[0]
        if i + 1 < len(expected) and expected[i + 1] in peaks:
            nxt = expected[i + 1]
            if row[1] == nxt[1] and row[2] == nxt[2]:
                end = nxt[0]
        if regions and regions[-1][1] == row[0]:
            regions[-1] = (regions[-1][0], end)
        else:
            regions.append((row[0], end))
    reported_regions = data.get("critical_regions")
    valid_regions = (isinstance(reported_regions, list) and len(reported_regions) == len(regions)
                     and all(isinstance(r, dict) and set(r) == {"x_start_mm", "x_end_mm"}
                             and _finite(r["x_start_mm"]) and _finite(r["x_end_mm"])
                             for r in reported_regions))
    if valid_regions:
        valid_regions = all(r["x_start_mm"] == a and r["x_end_mm"] == b
                            for r, (a, b) in zip(reported_regions, regions))
    review.add("critical_regions", valid_regions,
               "critical tie/plateau regions mismatch")
    if not planes[0]["loads"] and not planes[1]["loads"]:
        review.add("both_zero", critical == 0 and regions == [(0.0, span)],
                   "empty planes must give zero resultant across full span")
