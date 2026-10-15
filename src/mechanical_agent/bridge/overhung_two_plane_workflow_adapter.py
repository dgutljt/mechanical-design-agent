"""Fixed-module JSON adapter; deliberately not registered as a Native Tool."""

import json
import sys

from mechanical_agent.bridge.torque_adapter import CONTRACT_VERSION, MAX_INPUT_BYTES
from mechanical_agent.workflows.verified_overhung_two_plane_shaft_strength import (
    WORKFLOW_ID, run_verified_overhung_two_plane_shaft_strength_chain,
)

OPERATION = WORKFLOW_ID
MAX_LOAD_RECORDS = 128


def _failure(code, message):
    return {"contract_version": CONTRACT_VERSION, "operation": OPERATION, "ok": False,
            "error": {"code": code, "message": message}, "metadata": {}}


def process(request):
    if (not isinstance(request, dict) or set(request) != {"contract_version", "operation", "input"}
            or request["contract_version"] != CONTRACT_VERSION or request["operation"] != OPERATION):
        return _failure("INVALID_TOOL_INPUT", "Expected supported contract_version, operation and input only")
    inputs = request["input"]
    if not isinstance(inputs, dict):
        return _failure("INVALID_TOOL_INPUT", "Expected raw input object")
    planes = [inputs.get(field) for field in ("plane_1_loads", "plane_2_loads")]
    if (any(not isinstance(plane, list) for plane in planes)
            or any(len(plane) > MAX_LOAD_RECORDS for plane in planes)
            or sum(len(plane) for plane in planes) > MAX_LOAD_RECORDS):
        return _failure("INVALID_TOOL_INPUT", "At most 128 raw load records total and per plane")
    try:
        result = run_verified_overhung_two_plane_shaft_strength_chain(inputs)
    except Exception:
        return _failure("INTERNAL_ADAPTER_ERROR", "Verified chain failed")
    return {"contract_version": CONTRACT_VERSION, "operation": OPERATION,
            "ok": result["status"] == "PASS", **result, "metadata": {}}


def main():
    try:
        if sys.argv[1:]:
            response = _failure("INVALID_TOOL_INPUT", "Unexpected command arguments")
        else:
            raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
            if len(raw) > MAX_INPUT_BYTES:
                response = _failure("INVALID_TOOL_INPUT", "Input exceeds byte limit")
            else:
                response = process(json.loads(raw.decode("utf-8"), parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v))))
        encoded = json.dumps(response, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        encoded = json.dumps(_failure("INVALID_TOOL_INPUT", "Invalid JSON request or non-finite response"))
    except Exception:
        encoded = json.dumps(_failure("INTERNAL_ADAPTER_ERROR", "Adapter failed"))
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
