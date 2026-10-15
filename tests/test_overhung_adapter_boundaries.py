"""14C-P1A adapter-only limits; numerical/public Python contracts unchanged."""
from copy import deepcopy
import io
import json
import math
import os
import struct
import subprocess
import sys

import pytest

from mechanical_agent.bridge import overhung_two_plane_workflow_adapter as adapter
from mechanical_agent.workflows import verified_overhung_two_plane_shaft_strength as workflow

INPUT = dict(power_kw=5.5, speed_rpm=960, support_span_mm=600,
             left_overhang_mm=100, right_overhang_mm=100, plane_1_loads=[],
             plane_2_loads=[], allowable_shear_mpa=40, assume_constant_torque_over_shaft=True)


def request(inputs):
    return dict(contract_version="1", operation=adapter.OPERATION, input=inputs)


def with_loads(a, b):
    return {**deepcopy(INPUT), "plane_1_loads": [dict(load_n=(-1)**i, position_mm=0) for i in range(a)],
            "plane_2_loads": [dict(load_n=0, position_mm=0) for _ in range(b)]}


def failed(value):
    assert value["ok"] is False
    assert value["error"]["code"] == "INVALID_TOOL_INPUT"
    assert "results" not in value and "lineage" not in value
    assert value.get("status") != "PASS"


@pytest.mark.parametrize("a,b", [(128, 0), (0, 128), (127, 1), (1, 127), (64, 64), (0, 0)])
def test_accept_raw_records_and_empty_planes(a, b):
    value = adapter.process(request(with_loads(a, b)))
    assert value["ok"]
    assert len(value["results"]["statics"]["plane_1"]["loads"]) == a
    assert len(value["results"]["statics"]["plane_2"]["loads"]) == b


@pytest.mark.parametrize("a,b", [(129, 0), (0, 129), (128, 1), (1, 128), (65, 64), (64, 65), (128, 128)])
def test_process_rejects_before_workflow_without_cli_limit(monkeypatch, a, b):
    monkeypatch.setattr(adapter, "run_verified_overhung_two_plane_shaft_strength_chain",
                        lambda _: pytest.fail("Workflow must not be reached"))
    failed(adapter.process(request(with_loads(a, b))))


def cli(payload):
    run = subprocess.run([sys.executable, "-m", adapter.__name__], input=payload,
                         capture_output=True, env={**os.environ, "PYTHONPATH": "src"}, check=True)
    assert not run.stderr
    return json.loads(run.stdout)


@pytest.mark.parametrize("size,ok", [(16_384, True), (16_385, False)])
def test_exact_full_stdin_bytes(size, ok):
    raw = json.dumps(request(with_loads(128, 0)), separators=(",", ":")).encode()
    payload = raw + b" " * (size - len(raw))
    assert len(payload) == size
    value = cli(payload)
    if ok:
        assert value["ok"]
    else:
        failed(value)


def test_stdin_bytes_rejected_before_json_and_workflow(monkeypatch, capsys):
    payload = json.dumps(request(with_loads(129, 0))).encode()
    payload += b" " * (16_385 - len(payload))
    monkeypatch.setattr(sys, "stdin", type("Stdin", (), {"buffer": io.BytesIO(payload)})())
    monkeypatch.setattr(sys, "argv", [adapter.__name__])
    monkeypatch.setattr(adapter.json, "loads", lambda *a, **k: pytest.fail("Must reject before JSON parsing"))
    monkeypatch.setattr(adapter, "run_verified_overhung_two_plane_shaft_strength_chain",
                        lambda _: pytest.fail("Must reject before workflow"))
    assert adapter.main() == 0
    # Restore json.loads before inspecting the output (same imported module).
    monkeypatch.undo()
    failed(json.loads(capsys.readouterr().out))


def test_count_and_byte_limit_both_exceeded():
    raw = json.dumps(request(with_loads(129, 0))).encode()
    assert len(raw) < 16_384
    failed(cli(raw))
    failed(cli(raw + b" " * (16_385 - len(raw))))


def test_unicode_utf8_size_and_rejection():
    raw = json.dumps(request({**INPUT, "command": "中" * 5500}), ensure_ascii=False).encode()
    assert len(raw.decode()) < 16_384 < len(raw)
    failed(cli(raw))


@pytest.mark.parametrize("updates", [
    {"torque_nm": 0}, {"reviews": {"torque": "PASS"}}, {"command": "python"},
    {"tool_path": "x"}, {"pythonExecutable": "x"}, {"power_kw": True},
    {"speed_rpm": "960"}, {"power_kw": None}, {"power_kw": math.inf},
    {"power_kw": math.nan}, {"power_kw": 10**400},
    {"assume_constant_torque_over_shaft": 1}, {"assume_constant_torque_over_shaft": False},
    {"plane_1_loads": ()}, {"plane_2_loads": None},
    {"plane_1_loads": [dict(load_n=1, position_mm=0, torque_nm=1)]},
    {"plane_1_loads": [dict(load_n="1", position_mm=0)]},
    {"plane_1_loads": [dict(load_n=math.inf, position_mm=0)]},
])
def test_invalid_process_inputs_fail_closed(updates):
    failed(adapter.process(request({**deepcopy(INPUT), **updates})))


@pytest.mark.parametrize("payload", [b"NaN", b"{}", b"\xff", b'{"input": Infinity}',
    json.dumps({**request(INPUT), "command": "x"}).encode()])
def test_invalid_cli_inputs_fail_closed(payload):
    failed(cli(payload))


def test_public_workflow_still_accepts_129():
    value = workflow.run_verified_overhung_two_plane_shaft_strength_chain(with_loads(129, 0))
    assert value["status"] == "PASS"
    assert len(value["results"]["statics"]["plane_1"]["loads"]) == 129


def bits(value):
    return struct.pack("!d", value)


@pytest.mark.parametrize("load", [-0.0, math.nextafter(1.0, math.inf), math.ulp(0.0),
    sys.float_info.max, -sys.float_info.max])
def test_binary64_cli_roundtrip(load):
    inputs = {**deepcopy(INPUT), "power_kw": -0.0, "right_overhang_mm": -0.0,
              "plane_1_loads": [dict(load_n=load, position_mm=-0.0)]}
    value = cli(json.dumps(request(inputs), allow_nan=False).encode())
    assert value["ok"]
    assert bits(value["results"]["statics"]["plane_1"]["loads"][0]["load_n"]) == bits(load)
    for v in [value["results"]["torque"]["power_kw"], value["results"]["torque"]["torque_nm"],
              value["lineage"]["torque"]["exact_value"], value["results"]["combined"]["torque_nm"],
              value["results"]["statics"]["right_overhang_mm"],
              value["results"]["statics"]["plane_1"]["loads"][0]["position_mm"]]:
        assert bits(v) == bits(-0.0)


def test_subnormal_negative_component_in_serialized_lineage():
    inputs = {**deepcopy(INPUT), "support_span_mm": 1, "left_overhang_mm": 1,
              "right_overhang_mm": 0, "plane_1_loads": [dict(load_n=2 * math.ulp(0.0), position_mm=.5)]}
    value = cli(json.dumps(request(inputs)).encode())
    assert value["ok"]
    station = next(s for s in value["lineage"]["critical_stations"] if s["position_mm"] == .5)
    assert bits(station["plane_1_moment_nmm"]) == bits(-0.0)
