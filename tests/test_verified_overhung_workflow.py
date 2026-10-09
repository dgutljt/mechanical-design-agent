"""Phase 14B-2 review gates, exact handoff and raw-input boundary."""

from copy import deepcopy
from dataclasses import replace
import json
import math
import os
import subprocess
import sys

import pytest

from mechanical_agent.workflows import verified_overhung_two_plane_shaft_strength as w
from mechanical_agent.bridge import overhung_two_plane_workflow_adapter as adapter
from mechanical_agent.review import engineering_result as reviewer

INPUT = dict(power_kw=5.5, speed_rpm=960, support_span_mm=600,
             left_overhang_mm=100, right_overhang_mm=100,
             plane_1_loads=[dict(load_n=-1000, position_mm=-100)],
             plane_2_loads=[dict(load_n=500, position_mm=700)],
             allowable_shear_mpa=40, assume_constant_torque_over_shaft=True)


def request(inputs):
    return dict(contract_version="1", operation=adapter.OPERATION, input=inputs)


def test_success_exact_handoff_and_provenance(monkeypatch):
    actual = w.calculate_solid_shaft_min_diameter_combined
    calls = []
    def capture(m, t, stress):
        calls.append((m, t))
        return actual(m, t, stress)
    monkeypatch.setattr(w, "calculate_solid_shaft_min_diameter_combined", capture)
    value = adapter.process(request(INPUT))
    assert value["ok"] and value["workflow_id"] == w.WORKFLOW_ID
    assert value["reviews"] == dict(torque="PASS", statics="PASS", combined="PASS")
    torque, statics, combined = (value["results"][k] for k in ("torque", "statics", "combined"))
    assert w._exact(calls[0][0], statics["critical_resultant_bending_moment_nm"])
    assert w._exact(calls[0][1], torque["torque_nm"])
    for name, source, field in (("torque", torque, "torque_nm"),
                                ("bending_moment", statics, "critical_resultant_bending_moment_nm")):
        assert w._exact(value["lineage"][name]["exact_value"], source[field])
        assert w._exact(value["lineage"][name]["exact_value"], combined[name + "_nm"])
    for field in ("critical_stations", "critical_regions"):
        assert w._exact(value["lineage"][field], statics[field])
    assert all({"position_mm", "plane_1_moment_nmm", "plane_2_moment_nmm"} <= set(s)
               for s in value["lineage"]["critical_stations"])
    assert set(value["provenance"]) == set(w.REGISTRY_SOURCES)
    for field in ("plane_1", "plane_2"):
        assert value["lineage"]["nested_plane_models"][field]["source_model_id"] == w.NESTED_MODEL_ID
        assert statics[field]["model_id"] == w.NESTED_MODEL_ID
    assert value["assume_constant_torque_over_shaft"] is True
    assert value["assumptions"] and value["limitations"]
    assert any(statics[p][r] < 0 for p in ("plane_1", "plane_2") for r in ("reaction_a_n", "reaction_b_n"))


@pytest.mark.parametrize("stage", ["torque", "statics", "combined"])
@pytest.mark.parametrize("mode", ["FAIL", "UNKNOWN", "exception"])
def test_review_fail_closed(monkeypatch, stage, mode):
    actual = w.review_bound_engineering_result
    ids = dict(zip(("torque", "statics", "combined"), w.MODEL_SOURCES))
    called = []
    combined = w.calculate_solid_shaft_min_diameter_combined
    def calculate(*args):
        called.append(True)
        return combined(*args)
    def reject(data):
        result = actual(data)
        if data["model_id"] == ids[stage]:
            if mode == "exception":
                raise RuntimeError("Reviewer unavailable")
            result.status = mode
        return result
    monkeypatch.setattr(w, "review_bound_engineering_result", reject)
    monkeypatch.setattr(w, "calculate_solid_shaft_min_diameter_combined", calculate)
    value = adapter.process(request(INPUT))
    assert not value["ok"] and value["error"]["code"] == "REVIEW_FAIL"
    assert "results" not in value and "lineage" not in value
    assert bool(called) == (stage == "combined")


@pytest.mark.parametrize("field", ["torque_nm", "bending_moment_nm", "min_diameter_mm", "reviews", "review_status", "torque_result", "module", "command"])
def test_forged_fields_rejected(monkeypatch, field):
    monkeypatch.setattr(w, "calculate_transmitted_torque", lambda *a: pytest.fail("calculator reached"))
    for inputs in ({**INPUT, field: "PASS"}, {**INPUT, "plane_1_loads": [{"load_n": 1, "position_mm": 0, field: 1}]}):
        assert adapter.process(request(inputs))["error"]["code"] == "INVALID_TOOL_INPUT"


@pytest.mark.parametrize("value", [False, 1, 0, "true", None, [], {}])
def test_confirmation_strict(value):
    assert adapter.process(request({**INPUT, "assume_constant_torque_over_shaft": value}))["error"]["code"] == "INVALID_TOOL_INPUT"


def test_confirmation_missing():
    inputs = deepcopy(INPUT)
    del inputs["assume_constant_torque_over_shaft"]
    assert not adapter.process(request(inputs))["ok"]


@pytest.mark.parametrize("model_id", list(w.REGISTRY_SOURCES))
@pytest.mark.parametrize("fault", ["missing", "model", "module", "sources", "source_ids", "empty", "criterion"])
def test_provenance_failure(monkeypatch, model_id, fault):
    actual = w.resolve_model_provenance
    def broken(mid):
        value = deepcopy(actual(mid))
        if mid != model_id:
            return value
        if fault == "missing":
            raise FileNotFoundError("Registry missing")
        if fault in ("model", "module", "source_ids"):
            key = {"model": "model_id", "module": "calculator_module", "source_ids": "source_ids"}[fault]
            value["model"][key] = "wrong"
        elif fault == "sources":
            value["sources"][0]["id"] = "wrong"
        elif fault == "empty":
            value["sources"] = []
        elif mid == "solid_shaft_combined_tresca_v1":
            value["model"]["criterion"] = "wrong"
        else:
            value["model"]["limitations"] = []
        return value
    monkeypatch.setattr(w, "resolve_model_provenance", broken)
    value = adapter.process(request(INPUT))
    assert not value["ok"] and value["error"]["code"] == "PROVENANCE_ERROR"
    assert "results" not in value


def test_signed_zero_and_lineage_tampering(monkeypatch):
    inputs = {**INPUT, "power_kw": -0.0}
    value = adapter.process(request(inputs))
    assert value["ok"]
    assert value["lineage"]["torque"]["exact_value"].hex() == "-0x0.0p+0"
    actual = w.calculate_solid_shaft_min_diameter_combined
    monkeypatch.setattr(w, "calculate_solid_shaft_min_diameter_combined",
                        lambda *a: replace(actual(*a), torque_nm=0.0))
    value = adapter.process(request(inputs))
    assert not value["ok"] and value["error"]["code"] == "LINEAGE_ERROR"
    assert not w._exact([{"x": -0.0}], [{"x": 0.0}])


@pytest.mark.parametrize("field", ["torque_nm", "bending_moment_nm"])
def test_one_ulp_handoff_change_rejected(monkeypatch, field):
    actual = w.calculate_solid_shaft_min_diameter_combined
    def changed(*args):
        result = actual(*args)
        return replace(result, **{field: math.nextafter(getattr(result, field), math.inf)})
    monkeypatch.setattr(w, "calculate_solid_shaft_min_diameter_combined", changed)
    value = adapter.process(request(INPUT))
    assert not value["ok"] and value["error"]["code"] == "LINEAGE_ERROR"


@pytest.mark.parametrize("stage", ["torque", "statics", "combined"])
def test_corrupt_calculator_result_rejected(monkeypatch, stage):
    names = dict(torque="calculate_transmitted_torque",
                 statics="calculate_two_support_overhung_two_plane_point_loads",
                 combined="calculate_solid_shaft_min_diameter_combined")
    fields = dict(torque="torque_nm", statics="critical_resultant_bending_moment_nm", combined="min_diameter_mm")
    actual = getattr(w, names[stage])
    monkeypatch.setattr(w, names[stage], lambda *a: replace(actual(*a), **{fields[stage]: -999.0}))
    value = adapter.process(request(INPUT))
    assert not value["ok"] and value["error"]["code"] == "REVIEW_FAIL"
    assert value["reviews"][stage] == "FAIL" and "results" not in value


def test_reviewer_cannot_overwrite_source(monkeypatch):
    actual = w.review_bound_engineering_result
    def mutate(data):
        review = actual(data)
        data.clear()
        return review
    monkeypatch.setattr(w, "review_bound_engineering_result", mutate)
    assert adapter.process(request(INPUT))["ok"]


@pytest.mark.parametrize("loads", [[], [{"load_n": 0.0, "position_mm": 200}],
    [{"load_n": -1000, "position_mm": -100}, {"load_n": -1000, "position_mm": 700}]])
def test_zero_plane_and_tied_regions(loads):
    value = adapter.process(request({**INPUT, "plane_1_loads": loads, "plane_2_loads": []}))
    assert value["ok"]
    statics = value["results"]["statics"]
    if not loads or loads[0]["load_n"] == 0:
        assert statics["critical_regions"] == [{"x_start_mm": -100.0, "x_end_mm": 700.0}]
    else:
        assert [s["position_mm"] for s in statics["critical_stations"]] == [0.0, 600.0]
        assert statics["critical_regions"] == [{"x_start_mm": 0.0, "x_end_mm": 600.0}]


@pytest.mark.parametrize("updates", [dict(power_kw=float("inf")), dict(speed_rpm=0),
    dict(support_span_mm=0), dict(left_overhang_mm=0, right_overhang_mm=0),
    dict(allowable_shear_mpa=True), dict(allowable_shear_mpa=0),
    dict(power_kw=1e308), dict(support_span_mm=10**400),
    dict(plane_1_loads=[dict(load_n=float("nan"), position_mm=0)])])
def test_numeric_boundaries_fail_closed(updates):
    value = adapter.process(request({**INPUT, **updates}))
    assert not value["ok"] and "results" not in value


def test_subnormal_components_preserved():
    tiny = math.nextafter(0.0, math.inf)
    value = adapter.process(request({**INPUT, "support_span_mm": 1, "left_overhang_mm": 1,
        "right_overhang_mm": 0, "plane_1_loads": [dict(load_n=2*tiny, position_mm=.5)], "plane_2_loads": []}))
    assert value["ok"]
    station = next(s for s in value["lineage"]["critical_stations"] if s["position_mm"] == .5)
    assert station["plane_1_moment_nmm"].hex() == "-0x0.0p+0"


def test_separated_tied_danger_sections():
    value = adapter.process(request({**INPUT, "plane_1_loads": [
        dict(load_n=-1000, position_mm=-100), dict(load_n=1000, position_mm=700)],
        "plane_2_loads": []}))
    assert value["ok"]
    assert value["lineage"]["critical_regions"] == [
        dict(x_start_mm=0.0, x_end_mm=0.0), dict(x_start_mm=600.0, x_end_mm=600.0)]
    stations = value["lineage"]["critical_stations"]
    assert [s["position_mm"] for s in stations] == [0.0, 600.0]
    assert stations[0]["plane_1_moment_nmm"] == -stations[1]["plane_1_moment_nmm"]


def test_cli_fixed_contract():
    env = {**os.environ, "PYTHONPATH": "src"}
    for payload, args in ((json.dumps(request(INPUT)), []), ("NaN", []),
                          ("{}", ["--module", "evil"]), ("x" * 16385, [])):
        run = subprocess.run([sys.executable, "-m", adapter.__name__, *args], input=payload,
                             text=True, capture_output=True, env=env, check=True)
        value = json.loads(run.stdout)
        assert value["ok"] == (not args and payload.startswith('{"contract_version"'))


@pytest.mark.parametrize("replacement", ["ulp", "power", "speed", "zero_sign"])
def test_upstream_torque_bound_to_request(monkeypatch, replacement):
    actual = w.calculate_transmitted_torque
    inputs = {**INPUT, "power_kw": -0.0} if replacement == "zero_sign" else INPUT
    def substitute(power, speed):
        if replacement == "power":
            return actual(55, speed)
        if replacement == "speed":
            return actual(power, 1920)
        result = actual(power, speed)
        return replace(result, torque_nm=(0.0 if replacement == "zero_sign"
                       else math.nextafter(result.torque_nm, math.inf)))
    monkeypatch.setattr(w, "calculate_transmitted_torque", substitute)
    monkeypatch.setattr(w, "calculate_solid_shaft_min_diameter_combined", lambda *a: pytest.fail("handoff reached"))
    value = adapter.process(request(inputs))
    assert not value["ok"] and value["error"]["code"] == "REQUEST_BINDING_ERROR"
    assert value["reviews"]["combined"] == "NOT_RUN"
    assert "results" not in value and "lineage" not in value


@pytest.mark.parametrize("replacement", ["empty", "plane_1", "plane_2", "position", "sign", "duplicate", "geometry", "swap"])
def test_upstream_statics_bound_to_request(monkeypatch, replacement):
    actual = w.calculate_two_support_overhung_two_plane_point_loads
    inputs = {**INPUT, "plane_1_loads": [dict(load_n=-500, position_mm=-100), dict(load_n=-500, position_mm=-100)]}
    def substitute(span, left, right, p1, p2):
        if replacement == "empty":
            p1, p2 = [], []
        elif replacement == "plane_1":
            p1 = []
        elif replacement == "plane_2":
            p2 = []
        elif replacement == "position":
            p1 = [w.PointLoad(-500, -50), w.PointLoad(-500, -100)]
        elif replacement == "sign":
            p1 = [w.PointLoad(500, -100), w.PointLoad(500, -100)]
        elif replacement == "duplicate":
            p1 = [w.PointLoad(-1000, -100)]
        elif replacement == "geometry":
            span = 650
        elif replacement == "swap":
            p1, p2 = p2, p1
        return actual(span, left, right, p1, p2)
    monkeypatch.setattr(w, "calculate_two_support_overhung_two_plane_point_loads", substitute)
    monkeypatch.setattr(w, "calculate_solid_shaft_min_diameter_combined", lambda *a: pytest.fail("handoff reached"))
    value = adapter.process(request(inputs))
    assert not value["ok"] and value["error"]["code"] == "REQUEST_BINDING_ERROR"
    assert "results" not in value and "lineage" not in value


def test_snapshot_cannot_be_changed_by_calculator_arguments(monkeypatch):
    actual = w.calculate_two_support_overhung_two_plane_point_loads
    def mutate(span, left, right, p1, p2):
        p1.clear()
        p2.clear()
        return actual(span, left, right, p1, p2)
    monkeypatch.setattr(w, "calculate_two_support_overhung_two_plane_point_loads", mutate)
    original = deepcopy(INPUT)
    value = adapter.process(request(INPUT))
    assert not value["ok"] and value["error"]["code"] == "REQUEST_BINDING_ERROR"
    assert INPUT == original


def test_snapshot_normalizes_stably_without_merging_duplicates():
    inputs = {**INPUT, "left_overhang_mm": -0.0,
        "plane_1_loads": [dict(load_n=-20, position_mm=200), dict(load_n=-0.0, position_mm=0.0),
                          dict(load_n=10, position_mm=200), dict(load_n=-50, position_mm=50)],
        "plane_2_loads": []}
    value = adapter.process(request(inputs))
    assert value["ok"]
    loads = value["results"]["statics"]["plane_1"]["loads"]
    assert [load["load_n"] for load in loads] == [-0.0, -50.0, -20.0, 10.0]
    assert loads[0]["load_n"].hex() == "-0x0.0p+0"
    assert value["results"]["statics"]["left_overhang_mm"].hex() == "-0x0.0p+0"


@pytest.mark.parametrize("stage", ["torque", "statics", "combined"])
@pytest.mark.parametrize("fault", ["empty", "hidden_failure", "missing", "duplicate", "model",
    "version", "wrong_type", "check_type", "passed_type", "name_type", "message_type", "errors_type", "warnings_type"])
def test_reviewer_evidence_gate(monkeypatch, stage, fault):
    from types import SimpleNamespace
    actual = w.review_bound_engineering_result
    ids = dict(zip(("torque", "statics", "combined"), w.MODEL_SOURCES))
    def substitute(data):
        review = actual(data)
        if data["model_id"] != ids[stage]:
            return review
        if fault == "empty":
            review.checks = []
        elif fault == "hidden_failure":
            review.checks[0] = replace(review.checks[0], passed=False)
        elif fault == "missing":
            review.checks = [c for c in review.checks if c.name != "calculator_mapping"]
        elif fault == "duplicate":
            review.checks.append(review.checks[0])
        elif fault == "model":
            review.model_id = "solid_shaft_pure_torsion_v1"
        elif fault == "version":
            review.reviewer_version = "engineering_reviewer_v2"
        elif fault == "wrong_type":
            return SimpleNamespace(**{k: getattr(review, k) for k in review.__slots__})
        elif fault == "check_type":
            review.checks[0] = dict(name="json_object", passed=True, message="passed")
        elif fault == "passed_type":
            review.checks[0] = replace(review.checks[0], passed=1)
        elif fault == "name_type":
            review.checks[0] = replace(review.checks[0], name=None)
        elif fault == "message_type":
            review.checks[0] = replace(review.checks[0], message=None)
        elif fault == "errors_type":
            review.errors = ()
        elif fault == "warnings_type":
            review.warnings = [1]
        return review
    monkeypatch.setattr(w, "review_bound_engineering_result", substitute)
    value = adapter.process(request(INPUT))
    assert not value["ok"] and value["error"]["code"] == "REVIEW_FAIL"
    assert value["reviews"][stage] == "FAIL"
    assert "results" not in value and "lineage" not in value


@pytest.mark.parametrize("check_name", ["plane_1_station_0", "plane_2_segment_0_slope", "resultant_0", "plane_1_geometry"])
def test_dynamic_statics_evidence_cannot_be_removed(monkeypatch, check_name):
    actual = w.review_bound_engineering_result
    def substitute(data):
        review = actual(data)
        if data["model_id"] == "two_support_overhung_two_plane_point_load_v1":
            index = next(i for i, c in enumerate(review.checks) if c.name == check_name)
            del review.checks[index]
        return review
    monkeypatch.setattr(w, "review_bound_engineering_result", substitute)
    value = adapter.process(request(INPUT))
    assert not value["ok"] and value["error"]["code"] == "REVIEW_FAIL"


@pytest.mark.parametrize("fault", ["missing", "module", "source", "parse"])
def test_nested_registry_actual_resolution_errors(monkeypatch, fault):
    from mechanical_agent import knowledge_registry as registry
    actual = registry.get_model_card
    def broken(model_id):
        if model_id != w.NESTED_MODEL_ID:
            return actual(model_id)
        if fault == "missing":
            raise ValueError("Unknown model_id")
        if fault == "parse":
            import tomllib
            return tomllib.loads("not valid toml")
        card = deepcopy(actual(model_id))
        card["calculator_module" if fault == "module" else "source_ids"] = (
            "mechanical_agent.calculators.torque" if fault == "module" else ["oer_strength_materials_torsion"])
        return card
    monkeypatch.setattr(registry, "get_model_card", broken)
    value = adapter.process(request(INPUT))
    assert not value["ok"] and value["error"]["code"] == "PROVENANCE_ERROR"
    assert "results" not in value and "lineage" not in value


@pytest.mark.parametrize("stage,fault", [
    ("torque", "ulp"), ("torque", "other_power"),
    ("statics", "ulp"), ("combined", "half"), ("combined", "double"),
])
def test_native_bound_evidence_replay_rejected(monkeypatch, stage, fault):
    baseline = w.run_verified_overhung_two_plane_shaft_strength_chain(deepcopy(INPUT))
    assert baseline["status"] == "PASS"
    evidence = reviewer.review_bound_engineering_result(baseline["results"][stage])
    assert evidence.status == "PASS"
    names = dict(torque="calculate_transmitted_torque",
                 statics="calculate_two_support_overhung_two_plane_point_loads",
                 combined="calculate_solid_shaft_min_diameter_combined")
    fields = dict(torque="torque_nm", statics="critical_resultant_bending_moment_nm",
                  combined="min_diameter_mm")
    calculator = getattr(w, names[stage])
    def changed(*args):
        if fault == "other_power":
            return calculator(55, args[1])
        value = calculator(*args)
        original = getattr(value, fields[stage])
        modified = (original / 2 if fault == "half" else original * 2
                    if fault == "double" else math.nextafter(original, math.inf))
        return replace(value, **{fields[stage]: modified})
    actual = w.review_bound_engineering_result
    def replay(data):
        return deepcopy(evidence) if data["model_id"] == evidence.model_id else actual(data)
    monkeypatch.setattr(w, names[stage], changed)
    monkeypatch.setattr(w, "review_bound_engineering_result", replay)
    value = adapter.process(request(INPUT))
    assert not value["ok"] and value["error"]["code"] == "REVIEW_FAIL"
    assert value["reviews"][stage] == "FAIL"
    assert "results" not in value and "lineage" not in value
    if stage != "combined":
        assert value["reviews"]["combined"] == "NOT_RUN"


@pytest.mark.parametrize("stage", ["torque", "statics", "combined"])
@pytest.mark.parametrize("fault", ["nested", "type", "zero_sign", "order", "missing_binding", "legacy", "version", "purpose"])
def test_complete_checks_do_not_allow_object_mismatch(monkeypatch, stage, fault):
    actual = w.review_bound_engineering_result
    model_id = list(w.MODEL_SOURCES)[["torque", "statics", "combined"].index(stage)]
    def mismatch(data):
        if data["model_id"] != model_id:
            return actual(data)
        source = deepcopy(data)
        source["binding_test_metadata"] = {"values": [0.0, 1.0]}
        if fault == "nested":
            source["binding_test_metadata"]["values"][1] = 2.0
        elif fault == "type":
            source["binding_test_metadata"]["values"][1] = 1
        elif fault == "zero_sign":
            source["binding_test_metadata"]["values"][0] = -0.0
        elif fault == "order":
            source["binding_test_metadata"]["values"].reverse()
        # These extra fields do not change any legacy numerical check.
        result = actual(source if fault in ("nested", "type", "zero_sign", "order") else data)
        assert result.status == "PASS"
        if fault == "missing_binding":
            result.object_binding = None
        elif fault == "legacy":
            return reviewer.review_engineering_result(data)
        elif fault in ("version", "purpose"):
            result.object_binding = replace(result.object_binding, **{fault: "wrong"})
        return result
    monkeypatch.setattr(w, "review_bound_engineering_result", mismatch)
    value = adapter.process(request(INPUT))
    assert not value["ok"] and value["reviews"][stage] == "FAIL"
    assert "results" not in value


@pytest.mark.parametrize("a,b", [
    (0.0, -0.0), (1, 1.0), (True, 1), (None, ""),
    (math.nextafter(0.0, math.inf), 0.0),
    (1.0, math.nextafter(1.0, math.inf)),
    (float.fromhex("0x1.fffffffffffffp+1023"), float("inf")),
    ([1, 2], [2, 1]), ({"x": []}, {"x": {}}),
    ({"a": "bc"}, {"ab": "c"}),
    ({"x": [{"y": -0.0}]}, {"x": [{"y": 0.0}]}),
])
def test_binding_strict_encoding(a, b):
    assert reviewer.engineering_object_binding(a) != reviewer.engineering_object_binding(b)


def test_binding_is_deterministic_and_dict_order_independent():
    a = {"z": [None, True, -0.0, 10**100, "中文"], "a": {"x": 1}}
    b = {"a": {"x": 1}, "z": a["z"]}
    assert reviewer.engineering_object_binding(a) == reviewer.engineering_object_binding(b)
    assert reviewer.engineering_object_binding(a) == reviewer.engineering_object_binding(deepcopy(a))


@pytest.mark.parametrize("value", [(1, 2), {1: "x"}, {"x": {1, 2}}, object()])
def test_binding_rejects_unsupported_types(value):
    with pytest.raises(ValueError):
        reviewer.review_bound_engineering_result(value)


@pytest.mark.parametrize("stage", ["torque", "statics", "combined"])
@pytest.mark.parametrize("failed", [False, True])
def test_native_and_legacy_review_contracts_match(stage, failed):
    from dataclasses import asdict
    baseline = w.run_verified_overhung_two_plane_shaft_strength_chain(deepcopy(INPUT))
    data = baseline["results"][stage]
    if failed:
        data["formula"] = 1
    before = deepcopy(data)
    old = reviewer.review_engineering_result(data)
    new = reviewer.review_bound_engineering_result(data)
    assert type(old) is reviewer.ReviewResult
    expected = asdict(old)
    assert set(expected) == {"status", "model_id", "checks", "errors", "warnings", "reviewer_version"}
    bound_fields = asdict(new)
    del bound_fields["object_binding"]
    assert expected == bound_fields
    assert old.status == ("FAIL" if failed else "PASS")
    assert new.object_binding == reviewer.engineering_object_binding(before)
    assert w._exact(data, before)


@pytest.mark.parametrize("stage", ["torque", "statics", "combined"])
def test_mutation_of_private_review_snapshot_fails_closed(monkeypatch, stage):
    model_id = list(w.MODEL_SOURCES)[["torque", "statics", "combined"].index(stage)]
    actual = reviewer.VERIFIERS[model_id]
    def mutate(data, evidence):
        actual(data, evidence)
        data["injected_after_checks"] = {"zero": -0.0}
    monkeypatch.setitem(reviewer.VERIFIERS, model_id, mutate)
    value = adapter.process(request(INPUT))
    assert not value["ok"] and value["reviews"][stage] == "FAIL"
    assert "results" not in value


def test_caller_mutation_during_review_cannot_change_private_snapshot(monkeypatch):
    from dataclasses import asdict
    data = asdict(w.calculate_transmitted_torque(5.5, 960))
    before = deepcopy(data)
    actual = reviewer.VERIFIERS[data["model_id"]]
    def mutate_caller(snapshot, evidence):
        data["torque_nm"] *= 2
        actual(snapshot, evidence)
    monkeypatch.setitem(reviewer.VERIFIERS, data["model_id"], mutate_caller)
    result = reviewer.review_bound_engineering_result(data)
    assert result.status == "PASS"
    assert result.object_binding == reviewer.engineering_object_binding(before)
    assert not w._review_evidence_valid(result, data, data["model_id"])
