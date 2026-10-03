"""One-shot JSON contract for the existing torque calculator, Reviewer, and Registry."""

from dataclasses import asdict
import json
from pathlib import Path
import sys
import tomllib

from mechanical_agent.calculators.torque import MODEL_ID, calculate_transmitted_torque
from mechanical_agent.knowledge_registry import find_knowledge_root, resolve_model_provenance
from mechanical_agent.review.engineering_result import review_engineering_result

CONTRACT_VERSION = "1"
OPERATION = "transmitted_torque_v1"
MAX_INPUT_BYTES = 16_384


def _version() -> str:
    root = find_knowledge_root().parent
    with (root / "pyproject.toml").open("rb") as stream:
        return tomllib.load(stream)["project"]["version"]


def _failure(code: str, message: str, details: dict | None = None) -> dict:
    return {
        "contract_version": CONTRACT_VERSION, "ok": False, "operation": OPERATION,
        "error": {"code": code, "message": message, "details": details or {}},
        "metadata": {},
    }


def probe() -> dict:
    """Expose only interpreter/package identity facts for bridge resolution."""
    root = find_knowledge_root().parent.resolve()
    return {
        "contract_version": CONTRACT_VERSION, "ok": True,
        "python_version": list(sys.version_info[:3]),
        "python_project_version": _version(),
        "module_source": str(Path(__file__).resolve()),
        "repository_root": str(root),
        "registry_reachable": bool(resolve_model_provenance(MODEL_ID)["sources"]),
    }


def process(request: object) -> dict:
    if not isinstance(request, dict) or set(request) != {"contract_version", "operation", "input"}:
        return _failure("INVALID_TOOL_INPUT", "Expected contract_version, operation, and input only")
    if request["contract_version"] != CONTRACT_VERSION:
        return _failure("INVALID_TOOL_INPUT", "Unsupported contract version")
    if request["operation"] != OPERATION:
        return _failure("INVALID_TOOL_INPUT", "Unsupported operation")
    inputs = request["input"]
    if not isinstance(inputs, dict) or set(inputs) != {"power_kw", "speed_rpm"}:
        return _failure("INVALID_TOOL_INPUT", "Expected power_kw and speed_rpm only")
    if any(isinstance(inputs[key], bool) or not isinstance(inputs[key], (int, float))
           for key in ("power_kw", "speed_rpm")):
        return _failure("INVALID_TOOL_INPUT", "Engineering inputs must be JSON numbers")
    try:
        calculator_result = asdict(calculate_transmitted_torque(**inputs))
    except (ValueError, OverflowError) as exc:
        return _failure("ENGINEERING_INPUT_ERROR", str(exc))
    except Exception:
        return _failure("CALCULATOR_ERROR", "Calculator failed")
    try:
        review = asdict(review_engineering_result(calculator_result))
    except Exception:
        return _failure("INTERNAL_ADAPTER_ERROR", "Reviewer invocation failed")
    if review["status"] != "PASS":
        return _failure("REVIEW_FAIL", "Deterministic Reviewer rejected calculator result", {
            "review": review,
        })
    try:
        provenance = resolve_model_provenance(MODEL_ID)
    except Exception:
        return _failure("PROVENANCE_ERROR", "Registry provenance resolution failed")
    return {
        "contract_version": CONTRACT_VERSION, "ok": True, "operation": OPERATION,
        "model_id": MODEL_ID, "calculator_result": calculator_result,
        "review": review, "provenance": provenance, "warnings": [],
        "metadata": {"python_project_version": _version()},
    }


def main() -> int:
    try:
        if sys.argv[1:] == ["--probe"]:
            response = probe()
        elif sys.argv[1:]:
            response = _failure("INVALID_TOOL_INPUT", "Unexpected command arguments")
        else:
            raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
            if len(raw) > MAX_INPUT_BYTES:
                response = _failure("INVALID_TOOL_INPUT", "Input exceeds byte limit")
            else:
                response = process(json.loads(raw.decode("utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value))))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        response = _failure("INVALID_TOOL_INPUT", "Invalid JSON request")
    except Exception:
        response = _failure("INTERNAL_ADAPTER_ERROR", "Adapter failed")
    print(json.dumps(response, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
