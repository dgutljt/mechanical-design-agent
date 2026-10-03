"""Native verified chain boundary tests."""

from contextlib import redirect_stdout
import io
import json

import pytest

from mechanical_agent.bridge import shaft_workflow_adapter as adapter
from mechanical_agent.review.engineering_result import ReviewResult
from mechanical_agent.workflows import verified_shaft_strength as workflow


REQUEST = {"contract_version": "1", "operation": "verified_shaft_strength_v1", "input": {
    "power_kw": 5.5, "speed_rpm": 960, "span_mm": 600,
    "loads": [{"load_n": 1000, "position_mm": 200},
              {"load_n": 500, "position_mm": 450}],
    "allowable_shear_mpa": 40}}


def test_v1_chain_exact_lineage_review_and_provenance(monkeypatch):
    original = adapter.run_verified_shaft_strength_chain
    calls = []

    def tracked(torque, statics, allowable):
        calls.append((torque, statics, allowable))
        return original(torque, statics, allowable)

    monkeypatch.setattr(adapter, "run_verified_shaft_strength_chain", tracked)
    result = adapter.process(REQUEST)
    assert result["ok"] is True
    assert len(calls) == 1
    assert result["workflow_id"] == workflow.WORKFLOW_ID
    assert result["reviews"] == {"torque": "PASS", "statics": "PASS", "combined": "PASS"}
    torque, statics, combined = (result["results"][key] for key in ("torque", "statics", "combined"))
    assert torque["torque_nm"] == 54.713541666666664
    assert statics["reaction_a_n"] == 791.6666666666667
    assert statics["reaction_b_n"] == 708.3333333333333
    assert statics["max_bending_moment_nm"] == 158.33333333333334
    assert combined["min_diameter_mm"] == 27.732717671613003
    for label, source in (("torque", torque), ("bending_moment", statics)):
        lineage = result["lineage"][label]
        assert lineage["exact_value"] == source[lineage["source_field"]]
        assert lineage["source_model_id"] == source["model_id"]
    assert combined["torque_nm"] == torque["torque_nm"]
    assert combined["bending_moment_nm"] == statics["max_bending_moment_nm"]
    assert set(result["provenance"]) == {
        "transmitted_torque_v1", "simply_supported_multi_point_load_v1",
        "solid_shaft_combined_tresca_v1"}
    for model_id, provenance in result["provenance"].items():
        assert provenance["model"]["model_id"] == model_id
        assert provenance["sources"]
    assert result == adapter.process(REQUEST)
    assert json.loads(json.dumps(result, allow_nan=False)) == result


@pytest.mark.parametrize("field,value", [
    ("torque_nm", 999999), ("max_bending_moment_nm", 1),
    ("pythonExecutable", "C:/fake/python.exe"), ("model_id", "fake")])
def test_intermediate_and_control_fields_rejected_at_adapter(field, value):
    request = {**REQUEST, "input": {**REQUEST["input"], field: value}}
    result = adapter.process(request)
    assert result["error"]["code"] == "INVALID_TOOL_INPUT"
    assert "results" not in result


def test_nested_load_tampering_rejected():
    inputs = {**REQUEST["input"], "loads": [{**REQUEST["input"]["loads"][0], "torque_nm": 999}]}
    assert adapter.process({**REQUEST, "input": inputs})["error"]["code"] == "INVALID_TOOL_INPUT"


@pytest.mark.parametrize("field,value", [("speed_rpm", 0), ("span_mm", -1),
                                          ("allowable_shear_mpa", -1)])
def test_invalid_engineering_input_has_no_results(field, value):
    inputs = {**REQUEST["input"], field: value}
    response = adapter.process({**REQUEST, "input": inputs})
    assert response["ok"] is False
    assert response["error"]["code"] == "ENGINEERING_INPUT_ERROR"
    assert "results" not in response


@pytest.mark.parametrize("failure_index", [0, 1, 2])
def test_reviewer_failure_never_releases_validated_result(monkeypatch, failure_index):
    original = workflow.review_engineering_result
    seen = []

    def injected(value):
        seen.append(value["model_id"])
        if len(seen) == failure_index + 1:
            return ReviewResult(status="FAIL", errors=["injected failure"])
        return original(value)

    monkeypatch.setattr(workflow, "review_engineering_result", injected)
    response = adapter.process(REQUEST)
    assert response["error"]["code"] == "REVIEW_FAIL"
    assert "results" not in response and "lineage" not in response
    if failure_index < 2:
        assert "solid_shaft_combined_tresca_v1" not in seen


def test_provenance_failure_has_no_results(monkeypatch):
    monkeypatch.setattr(adapter, "resolve_model_provenance", lambda *_: (_ for _ in ()).throw(ValueError("bad")))
    response = adapter.process(REQUEST)
    assert response["error"]["code"] == "PROVENANCE_ERROR"
    assert "results" not in response


def test_stdout_is_one_deterministic_json_object(monkeypatch):
    monkeypatch.setattr(adapter.sys, "argv", ["shaft_workflow_adapter"])
    monkeypatch.setattr(adapter.sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(REQUEST).encode())))
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        assert adapter.main() == 0
    assert len(stdout.getvalue().splitlines()) == 1
    assert json.loads(stdout.getvalue()) == adapter.process(REQUEST)
