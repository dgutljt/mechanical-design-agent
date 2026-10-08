"""Contract tests for the one-shot native Tool Python boundary."""

from contextlib import redirect_stdout
import io
import json
from unittest.mock import patch

from mechanical_agent.bridge import torque_adapter as adapter
from mechanical_agent.review.engineering_result import ReviewResult


REQUEST = {"contract_version": "1", "operation": "transmitted_torque_v1",
           "input": {"power_kw": 5.5, "speed_rpm": 960}}


def test_success_preserves_calculator_review_and_registry():
    result = adapter.process(REQUEST)
    assert result["ok"] is True
    assert result["calculator_result"]["torque_nm"] == 54.713541666666664
    assert result["review"]["status"] == "PASS"
    assert result["review"]["reviewer_version"] == "engineering_reviewer_v1"
    assert all(check["passed"] for check in result["review"]["checks"])
    assert result["provenance"]["model"]["model_id"] == result["model_id"]
    assert result["provenance"]["sources"]
    assert adapter.process(REQUEST) == result


def test_contract_and_operation_are_allowlisted():
    assert adapter.process({**REQUEST, "contract_version": "2"})["error"]["code"] == "INVALID_TOOL_INPUT"
    assert adapter.process({**REQUEST, "operation": "other"})["error"]["code"] == "INVALID_TOOL_INPUT"


def test_bad_engineering_input_and_bool_rejection():
    bad = {**REQUEST, "input": {"power_kw": 5.5, "speed_rpm": 0}}
    assert adapter.process(bad)["error"]["code"] == "ENGINEERING_INPUT_ERROR"
    bad["input"] = {"power_kw": True, "speed_rpm": 960}
    assert adapter.process(bad)["error"]["code"] == "INVALID_TOOL_INPUT"


def test_tool_input_cannot_select_executable_module_path_or_environment():
    for field in ("pythonExecutable", "module", "path", "env", "skip_reviewer"):
        bad = {**REQUEST, "input": {**REQUEST["input"], field: "override"}}
        result = adapter.process(bad)
        assert result["error"]["code"] == "INVALID_TOOL_INPUT"
        assert "calculator_result" not in result


def test_reviewer_fail_cannot_release_calculator_result():
    fail = ReviewResult(status="FAIL", errors=["injected failure"])
    with patch.object(adapter, "review_engineering_result", return_value=fail):
        result = adapter.process(REQUEST)
    assert result["ok"] is False
    assert result["error"]["code"] == "REVIEW_FAIL"
    assert "calculator_result" not in result
    assert "provenance" not in result


def test_provenance_failure_cannot_release_calculator_result():
    with patch.object(adapter, "resolve_model_provenance", side_effect=ValueError("injected")):
        result = adapter.process(REQUEST)
    assert result["error"]["code"] == "PROVENANCE_ERROR"
    assert "calculator_result" not in result


def test_stdout_is_single_json_object(monkeypatch):
    monkeypatch.setattr(adapter.sys, "argv", ["torque_adapter"])
    monkeypatch.setattr(adapter.sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(REQUEST).encode())))
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        assert adapter.main() == 0
    lines = stdout.getvalue().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["ok"] is True


def test_probe_identity():
    facts = adapter.probe()
    assert facts["python_version"][:2] >= [3, 12]
    assert facts["registry_reachable"] is True
    assert facts["python_project_version"] == "0.2.0"
