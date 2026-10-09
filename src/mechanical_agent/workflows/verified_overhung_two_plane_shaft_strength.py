"""Raw-input, fail-closed overhung shaft screening chain (Python only)."""

from copy import deepcopy
from collections import Counter
from dataclasses import asdict, dataclass
import math
import struct

from mechanical_agent.calculators.torque import calculate_transmitted_torque
from mechanical_agent.calculators.shaft_statics_signed import PointLoad
from mechanical_agent.calculators.shaft_statics_overhung_two_plane import calculate_two_support_overhung_two_plane_point_loads
from mechanical_agent.calculators.shaft_combined import calculate_solid_shaft_min_diameter_combined
from mechanical_agent.knowledge_registry import resolve_model_provenance
from mechanical_agent.review.engineering_result import (
    ReviewCheck, BoundReviewResult, ObjectBinding, engineering_object_binding,
    review_bound_engineering_result,
)

WORKFLOW_ID = "verified_overhung_two_plane_shaft_strength_chain_v1"
MODEL_SOURCES = {
    "transmitted_torque_v1": ("mechanical_agent.calculators.torque", "calculate_transmitted_torque", ["oer_strength_materials_torsion"]),
    "two_support_overhung_two_plane_point_load_v1": ("mechanical_agent.calculators.shaft_statics_overhung_two_plane", "calculate_two_support_overhung_two_plane_point_loads", ["engineering_statics_beam_equilibrium"]),
    "solid_shaft_combined_tresca_v1": ("mechanical_agent.calculators.shaft_combined", "calculate_solid_shaft_min_diameter_combined", ["air_force_stress_manual_shafting"]),
}
NESTED_MODEL_ID = "two_support_overhung_signed_point_load_v1"
REGISTRY_SOURCES = {
    **MODEL_SOURCES,
    NESTED_MODEL_ID: ("mechanical_agent.calculators.shaft_statics_overhung",
                      "calculate_two_support_overhung_signed_point_loads",
                      ["engineering_statics_beam_equilibrium"]),
}
INPUT_FIELDS = {"power_kw", "speed_rpm", "support_span_mm", "left_overhang_mm", "right_overhang_mm", "plane_1_loads", "plane_2_loads", "allowable_shear_mpa", "assume_constant_torque_over_shaft"}
ASSUMPTIONS = [
    "User explicitly accepts constant transmitted torque over the entire shaft for screening; the model does not verify the actual torque distribution.",
    "Power and speed describe the same steady shaft operating point; ideal simple supports and signed transverse point loads in orthogonal planes.",
    "Solid circular shaft, elastic steady-load Tresca theoretical minimum diameter only.",
]
LIMITATIONS = [
    "No axial torque distribution or transmission-element torque application positions are modeled.",
    "No fatigue, stress concentration, deflection, shoulders, axial loads, dynamics or final shaft design.",
]


def _number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except (OverflowError, ValueError):
        return False


def _exact(a, b):
    """Compare copied structures without losing binary64 signed zero."""
    if type(a) is not type(b):
        return False
    if isinstance(a, float):
        return struct.pack("!d", a) == struct.pack("!d", b)
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_exact(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(_exact(x, y) for x, y in zip(a, b))
    return a == b


@dataclass(frozen=True, slots=True)
class _RequestSnapshot:
    """Immutable binary64 request identity, independent of Calculator objects."""
    power_kw: float
    speed_rpm: float
    geometry: tuple[float, float, float]
    planes: tuple[tuple[tuple[float, float], ...], ...]

    @classmethod
    def capture(cls, inputs):
        return cls(float(inputs["power_kw"]), float(inputs["speed_rpm"]),
                   tuple(float(inputs[k]) for k in
                         ("support_span_mm", "left_overhang_mm", "right_overhang_mm")),
                   tuple(tuple(sorted(((float(load["load_n"]), float(load["position_mm"]))
                                       for load in inputs[field]), key=lambda item: item[1]))
                         for field in ("plane_1_loads", "plane_2_loads")))

    def matches(self, torque, statics):
        # Match the existing torque Calculator's binary64 evaluation order.
        # This validation value never replaces a reviewed machine field.
        expected_torque = 9550.0 * self.power_kw / self.speed_rpm
        if not all(_exact(torque.get(k), v) for k, v in (
                ("power_kw", self.power_kw), ("speed_rpm", self.speed_rpm),
                ("constant", 9550.0), ("torque_nm", expected_torque))):
            return False
        for data in (statics, statics["plane_1"], statics["plane_2"]):
            if not all(_exact(data.get(k), v) for k, v in zip(
                    ("support_span_mm", "left_overhang_mm", "right_overhang_mm"), self.geometry)):
                return False
        for field, loads in zip(("plane_1", "plane_2"), self.planes):
            expected = [{"load_n": f, "position_mm": x} for f, x in loads]
            if not _exact(statics[field].get("loads"), expected):
                return False
        return True


def _required_checks(data):
    """Exact evidence multiset for the unchanged engineering_reviewer_v1."""
    names = ["json_object", "model_registered", "required_fields", "finite_numeric_fields",
             "metadata_types", "provenance_resolved", "calculator_mapping", "calculator_exists"]
    model_id = data["model_id"]
    if model_id == "transmitted_torque_v1":
        names += ["input_ranges", "constant", "numerical_consistency"]
    elif model_id == "solid_shaft_combined_tresca_v1":
        names += ["input_ranges", "bending_units", "torque_units", "combined_load_term", "criterion"]
        names += ["zero_load" if data["torque_nm"] == 0 and data["bending_moment_nm"] == 0
                  else "inverse_equivalent_shear"]
    elif model_id == "two_support_overhung_two_plane_point_load_v1":
        names += ["coordinate_convention", "units", "common_stations", "resultant_stations_structure",
                  "critical_stations_structure", "resultant_count", "critical_value", "critical_stations", "critical_regions"]
        for field in ("plane_1", "plane_2"):
            plane = data[field]
            span, left, right = (plane[k] for k in
                                 ("support_span_mm", "left_overhang_mm", "right_overhang_mm"))
            events = {-left, 0.0, span, span + right, *(load["position_mm"] for load in plane["loads"])}
            plane_names = ["model", "geometry", "loads_structure", "stations_structure", "segments_structure",
                           "critical_moment_regions_structure", "model_id", "units", "sign_convention",
                           "load_domain", "load_order", "reaction_structure", "total_load", "force_equilibrium",
                           "moment_equilibrium", "reactions", "event_count", "free_end_moments",
                           "signed_extrema", "critical", "critical_regions", "geometry"]
            # The real Reviewer emits geometry twice: reconstruction and parent binding.
            plane_names += [f"station_{i}" for i in range(len(events))]
            for i in range(len(events) - 1):
                plane_names += [f"segment_{i}_{suffix}" for suffix in ("bounds", "shear", "moments", "slope")]
                if i:
                    plane_names += [f"segment_{i}_jump", f"segment_{i}_continuity"]
            names += [field + "_" + name for name in plane_names]
        common = {-data["left_overhang_mm"], 0.0, data["support_span_mm"],
                  data["support_span_mm"] + data["right_overhang_mm"],
                  *(load["position_mm"] for field in ("plane_1", "plane_2") for load in data[field]["loads"])}
        names += [f"resultant_{i}" for i in range(len(common))]
    else:
        raise ValueError("Unsupported review identity")
    return Counter(names)


def _review_evidence_valid(checked, data, model_id):
    if (type(checked) is not BoundReviewResult
            or type(checked.object_binding) is not ObjectBinding
            or checked.object_binding != engineering_object_binding(data)
            or type(checked.status) is not str or checked.status != "PASS"
            or type(checked.model_id) is not str or checked.model_id != model_id
            or type(checked.reviewer_version) is not str or checked.reviewer_version != "engineering_reviewer_v1"
            or type(checked.errors) is not list or checked.errors
            or type(checked.warnings) is not list or any(type(v) is not str for v in checked.warnings)
            or type(checked.checks) is not list or not checked.checks):
        return False
    if any(type(check) is not ReviewCheck or check.passed is not True
           or type(check.name) is not str or not check.name
           or type(check.message) is not str or not check.message for check in checked.checks):
        return False
    return Counter(check.name for check in checked.checks) == _required_checks(data)


def _provenance(model_id):
    provenance = resolve_model_provenance(model_id)
    card, sources = provenance["model"], provenance["sources"]
    module, function, source_ids = REGISTRY_SOURCES[model_id]
    if (card["model_id"] != model_id or card["calculator_module"] != module
            or card["calculator_function"] != function or card["source_ids"] != source_ids
            or not isinstance(sources, list) or [s["id"] for s in sources] != source_ids
            or any(not all(isinstance(s.get(k), str) and s[k] for k in
                           ("title", "url", "section", "source_type")) for s in sources)
            or not card.get("assumptions") or not card.get("limitations")):
        raise ValueError("Incomplete or incorrect Registry mapping")
    if model_id == "solid_shaft_combined_tresca_v1" and card.get("criterion") != "maximum shear stress (Tresca)":
        raise ValueError("Incorrect Registry criterion")
    return provenance


def run_verified_overhung_two_plane_shaft_strength_chain(inputs: object) -> dict:
    """Accept raw inputs only; never accept externally supplied machine results."""
    reviews = {label: "NOT_RUN" for label in ("torque", "statics", "combined")}

    def fail(code, message):
        return {"workflow_id": WORKFLOW_ID, "status": "FAIL", "reviews": reviews.copy(),
                "error": {"code": code, "message": message}}

    if not isinstance(inputs, dict) or set(inputs) != INPUT_FIELDS:
        return fail("INVALID_TOOL_INPUT", "Expected raw overhung shaft inputs only")
    if inputs["assume_constant_torque_over_shaft"] is not True:
        return fail("INVALID_TOOL_INPUT", "assume_constant_torque_over_shaft must be boolean true")
    if any(not _number(inputs[k]) for k in INPUT_FIELDS - {"plane_1_loads", "plane_2_loads", "assume_constant_torque_over_shaft"}):
        return fail("INVALID_TOOL_INPUT", "Engineering inputs must be finite JSON numbers")
    for field in ("plane_1_loads", "plane_2_loads"):
        loads = inputs[field]
        if not isinstance(loads, list) or any(not isinstance(load, dict)
                or set(load) != {"load_n", "position_mm"}
                or any(not _number(v) for v in load.values()) for load in loads):
            return fail("INVALID_TOOL_INPUT", "Loads require finite load_n and position_mm only")
    if inputs["allowable_shear_mpa"] <= 0:
        return fail("ENGINEERING_INPUT_ERROR", "allowable_shear_mpa must be positive")
    # Snapshot caller-owned data before computing; Reviewer gets a separate copy.
    inputs = deepcopy(inputs)
    try:
        snapshot = _RequestSnapshot.capture(inputs)
        torque = asdict(calculate_transmitted_torque(inputs["power_kw"], inputs["speed_rpm"]))
        statics = asdict(calculate_two_support_overhung_two_plane_point_loads(
            inputs["support_span_mm"], inputs["left_overhang_mm"], inputs["right_overhang_mm"],
            [PointLoad(**load) for load in inputs["plane_1_loads"]],
            [PointLoad(**load) for load in inputs["plane_2_loads"]]))
    except (ValueError, TypeError, OverflowError):
        return fail("ENGINEERING_INPUT_ERROR", "Upstream calculator rejected input")
    except Exception:
        return fail("CALCULATOR_ERROR", "Upstream calculator failed")

    def review(label, data, expected_model):
        if data.get("model_id") != expected_model:
            reviews[label] = "FAIL"
            return False
        try:
            checked = review_bound_engineering_result(deepcopy(data))
            passed = _review_evidence_valid(checked, data, expected_model)
            reviews[label] = "PASS" if passed else "FAIL"
            return passed
        except Exception:
            reviews[label] = "FAIL"
            return False

    torque_id, statics_id, combined_id = MODEL_SOURCES
    torque_pass = review("torque", torque, torque_id)
    statics_pass = review("statics", statics, statics_id)
    if not torque_pass or not statics_pass:
        return fail("REVIEW_FAIL", "Upstream Reviewer rejected a result")
    try:
        if not snapshot.matches(torque, statics):
            return fail("REQUEST_BINDING_ERROR", "Upstream result differs from the immutable request snapshot")
    except Exception:
        return fail("REQUEST_BINDING_ERROR", "Upstream request binding could not be verified")
    # Direct field transfer: no resultant recalculation, conversion or formatting.
    t, m = torque["torque_nm"], statics["critical_resultant_bending_moment_nm"]
    stations, regions = deepcopy(statics["critical_stations"]), deepcopy(statics["critical_regions"])
    try:
        combined = asdict(calculate_solid_shaft_min_diameter_combined(m, t, inputs["allowable_shear_mpa"]))
    except (ValueError, TypeError, OverflowError):
        return fail("ENGINEERING_INPUT_ERROR", "Combined calculator rejected input")
    except Exception:
        return fail("CALCULATOR_ERROR", "Combined calculator failed")
    if not review("combined", combined, combined_id):
        return fail("REVIEW_FAIL", "Combined Reviewer rejected result")
    if not (_exact(t, combined.get("torque_nm")) and _exact(m, combined.get("bending_moment_nm"))
            and inputs["allowable_shear_mpa"] == combined.get("allowable_shear_mpa")
            and _exact(stations, statics["critical_stations"]) and _exact(regions, statics["critical_regions"])):
        return fail("LINEAGE_ERROR", "Combined fields differ from reviewed source values")
    try:
        provenance = {model_id: _provenance(model_id) for model_id in REGISTRY_SOURCES}
    except Exception:
        return fail("PROVENANCE_ERROR", "Registry provenance resolution failed")
    return {"workflow_id": WORKFLOW_ID, "status": "PASS", "reviews": reviews,
            "results": {"torque": torque, "statics": statics, "combined": combined},
            "lineage": {
                "torque": {"source_model_id": torque_id, "source_field": "torque_nm", "source_unit": "N*m", "exact_value": t},
                "bending_moment": {"source_model_id": statics_id, "source_field": "critical_resultant_bending_moment_nm", "source_unit": "N*m", "exact_value": m},
                "critical_stations": stations, "critical_regions": regions,
                "coordinate_convention": statics["coordinate_convention"],
                "nested_plane_models": {field: {
                    "source_model_id": NESTED_MODEL_ID, "parent_model_id": statics_id,
                    "result_field": "statics." + field,
                    "component": "M_z" if field == "plane_1" else "-M_y",
                } for field in ("plane_1", "plane_2")}},
            "provenance": provenance,
            "assume_constant_torque_over_shaft": True,
            "assumptions": ASSUMPTIONS.copy(), "limitations": LIMITATIONS.copy()}
