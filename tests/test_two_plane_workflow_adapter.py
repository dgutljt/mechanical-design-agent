"""Phase 13E Native adapter gates and raw-input boundary."""

from mechanical_agent.bridge import two_plane_workflow_adapter as adapter


INPUT = {
    "power_kw": 5.5, "speed_rpm": 960, "span_mm": 600,
    "plane_1_loads": [{"load_n": -1000, "position_mm": 200}],
    "plane_2_loads": [{"load_n": -1000, "position_mm": 400}],
    "allowable_shear_mpa": 40,
}


def request(value=INPUT):
    return {"contract_version": "1", "operation": adapter.OPERATION, "input": value}


def test_raw_input_only_and_verified_lineage():
    result = adapter.process(request())
    assert result["ok"] is True
    assert result["workflow_id"] == "verified_two_plane_shaft_strength_chain_v1"
    assert result["reviews"] == {"torque": "PASS", "statics": "PASS", "combined": "PASS"}
    assert result["lineage"]["torque"]["exact_value"] == result["results"]["torque"]["torque_nm"]
    assert result["lineage"]["bending_moment"]["exact_value"] == result["results"]["statics"]["critical_resultant_bending_moment_nm"]
    assert result["lineage"]["critical_stations"] == result["results"]["statics"]["critical_stations"]
    assert result["lineage"]["critical_regions"] == result["results"]["statics"]["critical_regions"]
    assert set(result["provenance"]) == {
        "transmitted_torque_v1", "simply_supported_two_plane_point_load_v1",
        "solid_shaft_combined_tresca_v1",
    }


def test_forged_intermediate_fields_rejected_before_calculators(monkeypatch):
    monkeypatch.setattr(adapter, "calculate_transmitted_torque",
                        lambda *args: (_ for _ in ()).throw(AssertionError("calculator reached")))
    for field, value in (("torque_nm", 999), ("bending_moment_nm", 1),
                         ("min_diameter_mm", 2)):
        result = adapter.process(request({**INPUT, field: value}))
        assert result["ok"] is False
        assert result["error"]["code"] == "INVALID_TOOL_INPUT"
        assert "results" not in result
    poisoned = {**INPUT, "plane_1_loads": [{**INPUT["plane_1_loads"][0], "torque_nm": 999}]}
    assert adapter.process(request(poisoned))["error"]["code"] == "INVALID_TOOL_INPUT"


def test_reviewer_failure_never_releases_result(monkeypatch):
    from mechanical_agent.workflows import verified_two_plane_shaft_strength as workflow
    actual = adapter.run_verified_two_plane_shaft_strength_chain

    def reject(torque, statics, stress):
        statics["critical_resultant_bending_moment_nm"] = 1
        return actual(torque, statics, stress)

    monkeypatch.setattr(adapter, "run_verified_two_plane_shaft_strength_chain", reject)
    result = adapter.process(request())
    assert result["ok"] is False
    assert result["error"]["code"] == "REVIEW_FAIL"
    assert "results" not in result
