"""Signed point-force mechanics and reviewer rejection tests."""
from dataclasses import asdict
from copy import deepcopy
import math
import pytest

from mechanical_agent.calculators.shaft_statics_signed import (
    MODEL_ID, PointLoad, calculate_simply_supported_signed_point_loads as calc,
)
from mechanical_agent.calculators.shaft_statics_multi import (
    PointLoad as OldPointLoad, calculate_simply_supported_point_loads as old_calc,
)
from mechanical_agent.review.engineering_result import review_engineering_result
from mechanical_agent.knowledge_registry import resolve_model_provenance


def result(loads, span=600):
    value = asdict(calc(span, [PointLoad(*load) for load in loads]))
    assert value["model_id"] == MODEL_ID
    assert review_engineering_result(value).status == "PASS"
    return value


def test_v1_physical_magnitudes_and_provenance():
    old = old_calc(600, [OldPointLoad(1000, 200), OldPointLoad(500, 450)])
    new = result([(-1000, 200), (-500, 450)])
    assert new["reaction_a_n"] == pytest.approx(old.reaction_a_n)
    assert new["reaction_b_n"] == pytest.approx(old.reaction_b_n)
    assert new["critical_bending_moment_nm"] == pytest.approx(old.max_bending_moment_nm)
    assert new["reaction_a_n"] == pytest.approx(791.6666666666667)
    assert new["reaction_b_n"] == pytest.approx(708.3333333333333)
    assert new["critical_bending_moment_nm"] == pytest.approx(158.33333333333334)
    provenance = resolve_model_provenance(MODEL_ID)
    assert [source["id"] for source in provenance["sources"]] == ["engineering_statics_beam_equilibrium"]
    assert "project derivation" in provenance["model"]["derivation"]


def test_mixed_sign_negative_reaction_and_sign_reversal():
    value = result([(-1000, 200), (500, 450)])
    assert value["reaction_a_n"] > 0 > value["reaction_b_n"]
    assert value["signed_max_bending_moment_nmm"] > 0
    assert value["signed_min_bending_moment_nmm"] < 0
    assert value["critical_bending_moment_nmm"] == pytest.approx(
        value["signed_max_bending_moment_nmm"])
    assert any(s["shear_n"] < 0 for s in value["segments"])
    assert any(s["shear_n"] > 0 for s in value["segments"])


def test_negative_bending_can_control_absolute_critical():
    value = result([(1000, 200), (-500, 450)])
    assert value["signed_min_bending_moment_nmm"] < 0
    assert value["critical_bending_moment_nmm"] == pytest.approx(
        abs(value["signed_min_bending_moment_nmm"]))


def test_cancellation_and_coincident_loads():
    value = result([(1000, 200), (-1000, 200)])
    assert len(value["loads"]) == 2
    assert value["reaction_a_n"] == value["reaction_b_n"] == 0
    assert value["critical_bending_moment_nmm"] == 0
    assert value["critical_moment_regions"] == [{"x_start_mm": 0, "x_end_mm": 600}]
    result([(-100, 200), (-200, 200), (100, 400)])


def test_support_position_loads_and_zero_force():
    value = result([(-100, 0), (-200, 600), (0, 300)])
    assert value["reaction_a_n"] == 100
    assert value["reaction_b_n"] == 200
    assert value["critical_bending_moment_nmm"] == 0


def test_empty_plane_is_identically_zero():
    value = result([])
    assert value["loads"] == []
    assert value["stations"] == [
        {"position_mm": 0, "moment_nmm": 0},
        {"position_mm": 600, "moment_nmm": 0}]
    assert len(value["segments"]) == 1
    assert value["segments"][0]["shear_n"] == 0
    assert value["critical_moment_regions"] == [{"x_start_mm": 0, "x_end_mm": 600}]


def test_tied_peaks_and_plateau():
    tied = result([(-1000, 100), (2000, 200), (-2000, 400), (1000, 500)])
    assert tied["critical_moment_regions"] == [
        {"x_start_mm": 200, "x_end_mm": 200},
        {"x_start_mm": 400, "x_end_mm": 400}]
    plateau = result([(-1000, 200), (-1000, 400)])
    assert plateau["critical_moment_regions"] == [{"x_start_mm": 200, "x_end_mm": 400}]


@pytest.mark.parametrize("span,loads", [
    (0, []), (-1, []), (600, [PointLoad(1, -1)]),
    (600, [PointLoad(1, 601)]), (600, [PointLoad(float("nan"), 200)]),
    (600, [PointLoad(float("inf"), 200)]), (600, [PointLoad(1, float("nan"))]),
    (600, [PointLoad(1, float("inf"))]), (True, []),
    (600, "bad"), (600, [{"load_n": 1, "position_mm": 20}]),
])
def test_invalid_input(span, loads):
    with pytest.raises(ValueError):
        calc(span, loads)


@pytest.mark.parametrize("field,mutate", [
    ("reaction_a_n", lambda v: v.__setitem__("reaction_a_n", v["reaction_a_n"] + 10)),
    ("station moment", lambda v: v["stations"][1].__setitem__("moment_nmm", 123)),
    ("shear", lambda v: v["segments"][1].__setitem__("shear_n", 123)),
    ("moment slope", lambda v: v["segments"][1].__setitem__("moment_end_nmm", 123)),
    ("critical", lambda v: v.__setitem__("critical_bending_moment_nmm", 0)),
    ("region", lambda v: v["critical_moment_regions"][0].__setitem__("x_start_mm", 0)),
    ("units", lambda v: v["units"].__setitem__("moment", "N*m")),
    ("load position", lambda v: v["loads"][0].__setitem__("position_mm", 601)),
])
def test_reviewer_rejects_tampering(field, mutate):
    value = result([(-1000, 200), (500, 450)])
    bad = deepcopy(value)
    mutate(bad)
    assert review_engineering_result(bad).status == "FAIL", field
