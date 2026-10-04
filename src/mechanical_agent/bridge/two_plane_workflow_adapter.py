"""One-shot raw-input Native contract for reviewed two-plane shaft strength."""

from dataclasses import asdict
import json
import sys

from mechanical_agent.bridge.torque_adapter import CONTRACT_VERSION, MAX_INPUT_BYTES, _version
from mechanical_agent.calculators.torque import calculate_transmitted_torque
from mechanical_agent.calculators.shaft_statics_signed import PointLoad
from mechanical_agent.calculators.shaft_statics_two_plane import calculate_simply_supported_two_plane_point_loads
from mechanical_agent.knowledge_registry import resolve_model_provenance
from mechanical_agent.workflows.verified_two_plane_shaft_strength import run_verified_two_plane_shaft_strength_chain

OPERATION = "verified_two_plane_shaft_strength_v1"
INPUT_FIELDS = {"power_kw", "speed_rpm", "span_mm", "plane_1_loads", "plane_2_loads", "allowable_shear_mpa"}
LOAD_FIELDS = {"load_n", "position_mm"}


def _failure(code: str, message: str) -> dict:
    return {"contract_version": CONTRACT_VERSION, "ok": False, "operation": OPERATION,
            "error": {"code": code, "message": message, "details": {}}, "metadata": {}}


def _number(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float))


def process(request: object) -> dict:
    if not isinstance(request, dict) or set(request) != {"contract_version", "operation", "input"}:
        return _failure("INVALID_TOOL_INPUT", "Expected contract_version, operation, and input only")
    if request["contract_version"] != CONTRACT_VERSION or request["operation"] != OPERATION:
        return _failure("INVALID_TOOL_INPUT", "Unsupported contract version or operation")
    inputs = request["input"]
    if not isinstance(inputs, dict) or set(inputs) != INPUT_FIELDS:
        return _failure("INVALID_TOOL_INPUT", "Expected raw two-plane shaft inputs only")
    if any(not _number(inputs[key]) for key in INPUT_FIELDS - {"plane_1_loads", "plane_2_loads"}):
        return _failure("INVALID_TOOL_INPUT", "Engineering inputs must be JSON numbers")
    for field in ("plane_1_loads", "plane_2_loads"):
        loads = inputs[field]
        if not isinstance(loads, list) or any(
            not isinstance(load, dict) or set(load) != LOAD_FIELDS or
            any(not _number(load[key]) for key in LOAD_FIELDS) for load in loads
        ):
            return _failure("INVALID_TOOL_INPUT", f"{field} must contain load_n and position_mm only")
    if not inputs["plane_1_loads"] and not inputs["plane_2_loads"]:
        return _failure("INVALID_TOOL_INPUT", "At least one plane needs a point load")
    try:
        torque = asdict(calculate_transmitted_torque(inputs["power_kw"], inputs["speed_rpm"]))
        statics = asdict(calculate_simply_supported_two_plane_point_loads(
            inputs["span_mm"],
            [PointLoad(**load) for load in inputs["plane_1_loads"]],
            [PointLoad(**load) for load in inputs["plane_2_loads"]]))
    except (ValueError, TypeError, OverflowError) as exc:
        return _failure("ENGINEERING_INPUT_ERROR", str(exc))
    except Exception:
        return _failure("CALCULATOR_ERROR", "Upstream calculator failed")
    try:
        chain = run_verified_two_plane_shaft_strength_chain(torque, statics, inputs["allowable_shear_mpa"])
    except Exception:
        return _failure("INTERNAL_ADAPTER_ERROR", "Verified handoff failed")
    if "FAIL" in (chain.upstream_torque_review_status, chain.upstream_statics_review_status,
                  chain.combined_review_status):
        return _failure("REVIEW_FAIL", "Deterministic Reviewer rejected a chain result")
    if any(error.startswith("combined calculator failed:") for error in chain.errors):
        return _failure("ENGINEERING_INPUT_ERROR", "Combined calculator rejected engineering input")
    if chain.status != "PASS" or chain.combined_result is None:
        return _failure("LINEAGE_ERROR", "Verified handoff did not complete")
    try:
        if (chain.torque_nm != torque[chain.torque_source_field] or
                chain.bending_moment_nm != statics[chain.bending_moment_source_field] or
                chain.critical_stations != statics["critical_stations"] or
                chain.critical_regions != statics["critical_regions"]):
            return _failure("LINEAGE_ERROR", "Verified handoff source values differ")
    except (KeyError, TypeError):
        return _failure("LINEAGE_ERROR", "Verified handoff source fields are unavailable")
    try:
        provenance = {model_id: resolve_model_provenance(model_id) for model_id in (
            chain.torque_model_id, chain.statics_model_id, chain.combined_model_id)}
        version = _version()
    except Exception:
        return _failure("PROVENANCE_ERROR", "Registry provenance resolution failed")
    return {
        "contract_version": CONTRACT_VERSION, "ok": True, "operation": OPERATION,
        "workflow_id": chain.workflow_id,
        "results": {"torque": torque, "statics": statics, "combined": chain.combined_result},
        "reviews": {"torque": chain.upstream_torque_review_status,
                    "statics": chain.upstream_statics_review_status,
                    "combined": chain.combined_review_status},
        "lineage": {
            "torque": {"source_model_id": chain.torque_model_id,
                       "source_field": chain.torque_source_field, "exact_value": chain.torque_nm},
            "bending_moment": {"source_model_id": chain.statics_model_id,
                               "source_field": chain.bending_moment_source_field,
                               "exact_value": chain.bending_moment_nm},
            "critical_stations": chain.critical_stations,
            "critical_regions": chain.critical_regions,
        },
        "provenance": provenance, "warnings": chain.warnings,
        "metadata": {"python_project_version": version},
    }


def main() -> int:
    try:
        if sys.argv[1:]:
            response = _failure("INVALID_TOOL_INPUT", "Unexpected command arguments")
        else:
            raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
            if len(raw) > MAX_INPUT_BYTES:
                response = _failure("INVALID_TOOL_INPUT", "Input exceeds byte limit")
            else:
                request = json.loads(raw.decode("utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
                response = process(request)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        response = _failure("INVALID_TOOL_INPUT", "Invalid JSON request")
    except Exception:
        response = _failure("INTERNAL_ADAPTER_ERROR", "Adapter failed")
    print(json.dumps(response, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
