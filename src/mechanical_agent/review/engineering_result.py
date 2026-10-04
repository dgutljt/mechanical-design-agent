"""Deterministic review of untrusted engineering calculator JSON."""

from dataclasses import asdict, dataclass, field
from importlib import import_module
import json
import math
import sys

from mechanical_agent.knowledge_registry import resolve_model_provenance
from mechanical_agent.review.signed_statics import verify as _signed_statics

REL_TOL = 1e-12
ABS_TOL = 1e-12
CRITERION = "maximum shear stress (Tresca)"
CONTRACTS = {
    "transmitted_torque_v1": (
        "mechanical_agent.calculators.torque", "calculate_transmitted_torque",
        ("power_kw", "speed_rpm", "torque_nm", "constant"), ("formula",)),
    "solid_shaft_pure_torsion_v1": (
        "mechanical_agent.calculators.shaft_torsion", "calculate_solid_shaft_min_diameter",
        ("torque_nm", "torque_nmm", "allowable_shear_mpa", "min_diameter_mm"),
        ("formula", "assumptions")),
    "solid_shaft_combined_tresca_v1": (
        "mechanical_agent.calculators.shaft_combined",
        "calculate_solid_shaft_min_diameter_combined",
        ("bending_moment_nm", "bending_moment_nmm", "torque_nm", "torque_nmm",
         "allowable_shear_mpa", "combined_load_term_nmm", "min_diameter_mm"),
        ("criterion", "formula", "assumptions")),
    "simply_supported_point_load_v1": (
        "mechanical_agent.calculators.shaft_statics", "calculate_simply_supported_point_load",
        ("load_n", "span_mm", "load_position_mm", "reaction_a_n", "reaction_b_n",
         "max_bending_moment_nmm", "max_bending_moment_nm", "max_moment_position_mm"),
        ("formula", "assumptions")),
    "simply_supported_signed_multi_point_load_v1": (
        "mechanical_agent.calculators.shaft_statics_signed",
        "calculate_simply_supported_signed_point_loads",
        ("span_mm", "total_load_n", "reaction_a_n", "reaction_b_n",
         "signed_max_bending_moment_nmm", "signed_min_bending_moment_nmm",
         "critical_bending_moment_nmm", "critical_bending_moment_nm"),
        ("formula", "assumptions", "sign_convention")),
    "simply_supported_multi_point_load_v1": (
        "mechanical_agent.calculators.shaft_statics_multi", "calculate_simply_supported_point_loads",
        ("span_mm", "total_load_n", "reaction_a_n", "reaction_b_n",
         "max_bending_moment_nmm", "max_bending_moment_nm"),
        ("formula", "assumptions")),
}


@dataclass(frozen=True, slots=True)
class ReviewCheck:
    name: str
    passed: bool
    message: str


@dataclass(slots=True)
class ReviewResult:
    status: str = "PASS"
    model_id: str | None = None
    checks: list[ReviewCheck] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    reviewer_version: str = "engineering_reviewer_v1"

    def add(self, name: str, passed: bool, message: str) -> None:
        self.checks.append(ReviewCheck(
            name, passed, f"{name} check passed" if passed else message
        ))
        if not passed:
            self.status = "FAIL"
            self.errors.append(message)


def _close(actual: float, expected: float) -> bool:
    return math.isfinite(expected) and math.isclose(
        actual, expected, rel_tol=REL_TOL, abs_tol=ABS_TOL
    )


def _moment_close(actual: float, expected: float) -> bool:
    return math.isfinite(expected) and math.isclose(
        actual, expected, rel_tol=REL_TOL, abs_tol=1e-9
    )


def _finite_number(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, ValueError):
        return False


def _torque(data: dict, review: ReviewResult) -> None:
    power, speed = data["power_kw"], data["speed_rpm"]
    review.add("input_ranges", power >= 0 and speed > 0,
               "power_kw must be non-negative and speed_rpm must be positive")
    review.add("constant", data["constant"] == 9550.0, "constant must equal 9550.0")
    if power >= 0 and speed > 0:
        review.add("numerical_consistency", _close(data["torque_nm"], 9550 * power / speed),
                   "torque_nm numerical consistency check failed")


def _pure(data: dict, review: ReviewResult) -> None:
    torque, allowable, diameter = (
        data["torque_nm"], data["allowable_shear_mpa"], data["min_diameter_mm"]
    )
    review.add("input_ranges", torque >= 0 and allowable > 0,
               "torque_nm must be non-negative and allowable_shear_mpa must be positive")
    review.add("torque_units", _close(data["torque_nmm"], torque * 1000),
               "torque_nmm unit conversion check failed")
    if torque == 0:
        review.add("zero_load", diameter == 0,
                   "zero-load mathematical case requires min_diameter_mm = 0")
    elif torque > 0 and allowable > 0:
        if diameter <= 0:
            review.add("inverse_shear_stress", False,
                       "min_diameter_mm must be positive for nonzero load")
        else:
            tau_back = 16 * data["torque_nmm"] / (math.pi * diameter**3)
            review.add("inverse_shear_stress", _close(tau_back, allowable),
                       "min_diameter_mm numerical consistency check failed (inverse shear stress)")


def _combined(data: dict, review: ReviewResult) -> None:
    moment, torque, allowable, diameter = (
        data["bending_moment_nm"], data["torque_nm"],
        data["allowable_shear_mpa"], data["min_diameter_mm"]
    )
    moment_nmm, torque_nmm = data["bending_moment_nmm"], data["torque_nmm"]
    review.add("input_ranges", moment >= 0 and torque >= 0 and allowable > 0,
               "M and T must be non-negative and allowable_shear_mpa must be positive")
    review.add("bending_units", _close(moment_nmm, moment * 1000),
               "bending_moment_nmm unit conversion check failed")
    review.add("torque_units", _close(torque_nmm, torque * 1000),
               "torque_nmm unit conversion check failed")
    review.add("combined_load_term",
               _close(data["combined_load_term_nmm"], math.hypot(moment_nmm, torque_nmm)),
               "combined_load_term_nmm numerical consistency check failed")
    review.add("criterion", data["criterion"] == CRITERION,
               "criterion must match maximum shear stress (Tresca)")
    if moment == 0 and torque == 0:
        review.add("zero_load", diameter == 0,
                   "zero-load mathematical case requires min_diameter_mm = 0")
    elif moment >= 0 and torque >= 0 and allowable > 0:
        if diameter <= 0:
            review.add("inverse_equivalent_shear", False,
                       "min_diameter_mm must be positive for nonzero load")
        else:
            cubed = diameter**3
            sigma_b = 32 * moment_nmm / (math.pi * cubed)
            tau_t = 16 * torque_nmm / (math.pi * cubed)
            review.add("inverse_equivalent_shear",
                       _close(math.hypot(tau_t, sigma_b / 2), allowable),
                       "min_diameter_mm numerical consistency check failed (inverse Tresca stress)")


def _statics(data: dict, review: ReviewResult) -> None:
    load, span, position = data["load_n"], data["span_mm"], data["load_position_mm"]
    valid = load >= 0 and span > 0 and 0 <= position <= span
    review.add("input_ranges", valid,
               "load_n must be non-negative, span_mm positive, and load_position_mm within span")
    if not valid:
        return
    left, right = data["reaction_a_n"], data["reaction_b_n"]
    moment = data["max_bending_moment_nmm"]
    review.add("force_equilibrium", _close(left + right, load),
               "support reactions do not balance load")
    review.add("moment_equilibrium_a", _close(right * span, load * position),
               "moment equilibrium about A failed")
    review.add("moment_equilibrium_b", _close(left * span, load * (span - position)),
               "moment equilibrium about B failed")
    review.add("bending_from_a", _close(moment, left * position),
               "maximum moment does not match left reaction")
    review.add("bending_from_b", _close(moment, right * (span - position)),
               "maximum moment does not match right reaction")
    review.add("moment_units", _close(data["max_bending_moment_nm"], moment / 1000),
               "N*mm to N*m conversion failed")
    review.add("moment_position", _close(data["max_moment_position_mm"], position),
               "maximum moment position does not match load position")


def _multi_statics(data: dict, review: ReviewResult) -> None:
    nested = {
        "loads": ("load_n", "position_mm"),
        "segments": ("x_start_mm", "x_end_mm", "shear_n",
                     "moment_start_nmm", "moment_end_nmm"),
        "max_moment_regions": ("x_start_mm", "x_end_mm"),
    }
    for name, fields in nested.items():
        value = data.get(name)
        valid = (isinstance(value, list) and bool(value)
                 and all(isinstance(item, dict)
                         and all(field in item and _finite_number(item[field])
                                 for field in fields) for item in value))
        review.add(f"{name}_structure", valid, f"{name} must be a non-empty list of finite numeric records")
        if not valid:
            return
    span = data["span_mm"]
    loads = data["loads"]
    segments = data["segments"]
    regions = data["max_moment_regions"]
    valid = (span > 0 and all(item["load_n"] >= 0
                            and 0 <= item["position_mm"] <= span for item in loads))
    review.add("input_ranges", valid, "span must be positive; loads must be non-negative and within supports")
    if not valid:
        return
    ordered = all(a["position_mm"] <= b["position_mm"] for a, b in zip(loads, loads[1:]))
    review.add("load_order", ordered, "loads must be sorted by position")
    total = math.fsum(item["load_n"] for item in loads)
    left, right = data["reaction_a_n"], data["reaction_b_n"]
    review.add("total_load", _close(data["total_load_n"], total), "total load does not equal the sum of loads")
    review.add("force_equilibrium", _close(left + right, total), "support reactions do not balance loads")
    review.add("moment_equilibrium_a", _close(right * span, math.fsum(
        item["load_n"] * item["position_mm"] for item in loads)), "moment equilibrium about A failed")
    review.add("moment_equilibrium_b", _close(left * span, math.fsum(
        item["load_n"] * (span - item["position_mm"]) for item in loads)),
        "moment equilibrium about B failed")

    events = sorted({0.0, span, *(item["position_mm"] for item in loads)})
    review.add("segment_count", len(segments) == len(events) - 1,
               "segment count does not match independently reconstructed events")

    def moment_at(x: float) -> float:
        return math.fsum([left * x] + [
            -item["load_n"] * max(0, x - item["position_mm"]) for item in loads])

    event_moments = [moment_at(x) for x in events]
    review.add("support_moments", _moment_close(event_moments[0], 0) and _moment_close(event_moments[-1], 0),
               "support moments must be zero")
    for index, segment in enumerate(segments):
        if index >= len(events) - 1:
            break
        start, end = events[index:index + 2]
        boundary = _close(segment["x_start_mm"], start) and _close(segment["x_end_mm"], end)
        review.add(f"segment_{index}_boundary", boundary, "segment boundary does not match load events")
        shear = left - math.fsum(item["load_n"] for item in loads
                                 if item["position_mm"] <= start)
        review.add(f"segment_{index}_shear", _close(segment["shear_n"], shear),
                   "segment shear does not match left-side load sum")
        review.add(f"segment_{index}_moment_start",
                   _moment_close(segment["moment_start_nmm"], event_moments[index]),
                   "segment start moment is inconsistent")
        review.add(f"segment_{index}_moment_end",
                   _moment_close(segment["moment_end_nmm"], event_moments[index + 1]),
                   "segment end moment is inconsistent")
        review.add(f"segment_{index}_moment_slope", _moment_close(
            segment["moment_end_nmm"], segment["moment_start_nmm"]
            + segment["shear_n"] * (end - start)), "dM/dx = V check failed")
        if index:
            review.add(f"segment_{index}_continuity", _moment_close(
                segments[index - 1]["moment_end_nmm"], segment["moment_start_nmm"]),
                "bending moment jumps between segments")

    maximum = max(event_moments)
    review.add("maximum_moment", _close(data["max_bending_moment_nmm"], maximum),
               "maximum bending moment is inconsistent with event moments")
    review.add("moment_units", _close(data["max_bending_moment_nm"], maximum / 1000),
               "N*mm to N*m conversion failed")
    expected_regions = []
    for index, (position, moment) in enumerate(zip(events, event_moments)):
        if not _close(moment, maximum):
            continue
        end = position
        if index + 1 < len(events) and _close(event_moments[index + 1], maximum):
            shear = left - math.fsum(item["load_n"] for item in loads
                                     if item["position_mm"] <= position)
            if _close(shear, 0):
                end = events[index + 1]
        if expected_regions and _close(expected_regions[-1][1], position):
            expected_regions[-1] = (expected_regions[-1][0], end)
        else:
            expected_regions.append((position, end))
    region_valid = len(regions) == len(expected_regions)
    for index, region in enumerate(regions):
        start, end = region["x_start_mm"], region["x_end_mm"]
        region_valid = region_valid and 0 <= start <= end <= span
        if index:
            region_valid = region_valid and regions[index - 1]["x_end_mm"] < start
        if index < len(expected_regions):
            expected_start, expected_end = expected_regions[index]
            region_valid = region_valid and _close(start, expected_start) and _close(end, expected_end)
    review.add("max_moment_regions", region_valid,
               "maximum moment regions do not match event peaks or zero-shear plateaus")


VERIFIERS = {
    "transmitted_torque_v1": _torque,
    "solid_shaft_pure_torsion_v1": _pure,
    "solid_shaft_combined_tresca_v1": _combined,
    "simply_supported_point_load_v1": _statics,
    "simply_supported_multi_point_load_v1": _multi_statics,
    "simply_supported_signed_multi_point_load_v1": _signed_statics,
}


def review_engineering_result(result: dict) -> ReviewResult:
    """Check structure, provenance, and independent model consistency."""
    review = ReviewResult()
    if not isinstance(result, dict):
        review.add("json_object", False, "result must be a JSON object")
        return review
    review.add("json_object", True, "result is a JSON object")
    model_id = result.get("model_id")
    if not isinstance(model_id, str) or not model_id:
        review.add("model_id", False, "model_id must be a non-empty string")
        return review
    review.model_id = model_id
    if model_id not in VERIFIERS:
        review.add("model_registered", False, f"unknown model_id: {model_id}")
        return review
    review.add("model_registered", True, f"registered model_id: {model_id}")
    module, function, numeric, metadata = CONTRACTS[model_id]
    missing = [name for name in (*numeric, *metadata) if name not in result]
    if model_id == "simply_supported_signed_multi_point_load_v1":
        missing.extend(name for name in ("loads", "stations", "segments", "critical_moment_regions", "units")
                       if name not in result)
    if model_id == "simply_supported_multi_point_load_v1":
        missing.extend(name for name in ("loads", "segments", "max_moment_regions")
                       if name not in result)
    review.add("required_fields", not missing,
               "missing required fields: " + ", ".join(missing) if missing
               else "required fields present")
    if missing:
        return review
    invalid = [name for name in numeric if not _finite_number(result[name])]
    review.add("finite_numeric_fields", not invalid,
               "non-finite or invalid numeric fields: " + ", ".join(invalid) if invalid
               else "all numeric fields are finite numbers")
    bad_metadata = [name for name in metadata if not (
        isinstance(result[name], str) if name != "assumptions"
        else isinstance(result[name], list)
        and all(isinstance(item, str) for item in result[name])
    )]
    review.add("metadata_types", not bad_metadata,
               "invalid metadata fields: " + ", ".join(bad_metadata) if bad_metadata
               else "metadata fields have valid types")
    if invalid or bad_metadata:
        return review
    try:
        provenance = resolve_model_provenance(model_id)
        card, sources = provenance["model"], provenance["sources"]
        resolved = (card["model_id"] == model_id and isinstance(sources, list)
                    and bool(sources) and all(isinstance(source, dict) for source in sources)
                    and bool(card.get("calculator_module"))
                    and bool(card.get("calculator_function")))
        mapped = (card["calculator_module"] == module
                  and card["calculator_function"] == function)
        if model_id == "solid_shaft_combined_tresca_v1":
            mapped = mapped and card.get("criterion") == CRITERION
    except (OSError, ValueError, KeyError, TypeError) as exc:
        review.add("provenance_resolved", False, f"provenance resolution failed: {exc}")
        return review
    review.add("provenance_resolved", resolved,
               "model card and sources resolved" if resolved
               else "model card or sources are incomplete")
    review.add("calculator_mapping", mapped,
               "calculator/model card mapping matches" if mapped
               else "calculator/model card mapping mismatch")
    if not resolved or not mapped:
        return review
    try:
        calculator = import_module(module)  # module is from the fixed contract, never input
        exists = (calculator.MODEL_ID == model_id
                  and callable(getattr(calculator, function, None)))
    except (ImportError, AttributeError):
        exists = False
    review.add("calculator_exists", exists,
               "registered calculator module, function, or MODEL_ID is missing")
    if not exists:
        return review
    try:
        VERIFIERS[model_id](result, review)
    except (OverflowError, ZeroDivisionError, ValueError) as exc:
        review.add("numerical_consistency", False,
                   f"numerical consistency check failed: {exc}")
    return review


def main() -> int:
    try:
        result = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        review = ReviewResult()
        review.add("json_input", False, f"invalid JSON input: {exc}")
        print(json.dumps(asdict(review), allow_nan=False))
        return 2
    review = review_engineering_result(result)
    print(json.dumps(asdict(review), allow_nan=False))
    return 0 if review.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
