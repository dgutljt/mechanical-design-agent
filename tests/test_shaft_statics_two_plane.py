"""Two-plane same-station mechanics and independent Reviewer guards."""
from copy import deepcopy
from dataclasses import asdict
import math

import pytest

from mechanical_agent.calculators.shaft_statics_signed import PointLoad
from mechanical_agent.calculators.shaft_statics_two_plane import (
    MODEL_ID, calculate_simply_supported_two_plane_point_loads as calc,
)
from mechanical_agent.knowledge_registry import resolve_model_provenance
from mechanical_agent.review.engineering_result import review_engineering_result


def result(p1, p2, span=600):
    value = asdict(calc(span, [PointLoad(*v) for v in p1], [PointLoad(*v) for v in p2]))
    assert value["model_id"] == MODEL_ID
    assert review_engineering_result(value).status == "PASS"
    return value


def test_one_plane_only_and_same_location_orthogonal_loads():
    one = result([(-1000, 300)], [])
    assert one["critical_resultant_bending_moment_nmm"] == pytest.approx(150000)
    assert all(s["resultant_bending_moment_nmm"] == pytest.approx(abs(s["plane_1_moment_nmm"]))
               for s in one["resultant_stations"])
    other = result([], [(-1000, 300)])
    assert other["critical_resultant_bending_moment_nmm"] == pytest.approx(150000)
    both = result([(-1000, 300)], [(-1000, 300)])
    assert both["critical_resultant_bending_moment_nmm"] == pytest.approx(math.hypot(150000, 150000))
    assert both["critical_stations"][0]["position_mm"] == 300


def test_misaligned_plane_peaks_must_not_combine_separate_maxima():
    value = result([(-1000, 200)], [(-1000, 400)])
    assert value["plane_1"]["critical_moment_regions"] == [{"x_start_mm": 200, "x_end_mm": 200}]
    assert value["plane_2"]["critical_moment_regions"] == [{"x_start_mm": 400, "x_end_mm": 400}]
    assert value["common_stations_mm"] == [0, 200, 400, 600]
    actual = value["critical_resultant_bending_moment_nmm"]
    wrong = math.hypot(value["plane_1"]["critical_bending_moment_nmm"],
                       value["plane_2"]["critical_bending_moment_nmm"])
    assert actual == pytest.approx(math.hypot(400000 / 3, 200000 / 3))
    assert wrong == pytest.approx(math.hypot(400000 / 3, 400000 / 3))
    assert actual < wrong
    assert [s["position_mm"] for s in value["critical_stations"]] == [200, 400]
    assert value["critical_regions"] == [
        {"x_start_mm": 200, "x_end_mm": 200},
        {"x_start_mm": 400, "x_end_mm": 400},
    ]


def test_different_and_coincident_events_mixed_signs_and_cancellation():
    mixed = result([(-1000, 200), (500, 450)], [(200, 300), (-400, 500)])
    assert mixed["common_stations_mm"] == [0, 200, 300, 450, 500, 600]
    at_200 = mixed["resultant_stations"][1]
    assert at_200["plane_2_moment_nmm"] != 0  # 200 is not a plane-2 event
    result([(-1000, 200)], [(200, 200), (-300, 450)])
    canceled = result([(1000, 200), (-1000, 200)], [(-500, 300)])
    assert canceled["critical_resultant_bending_moment_nmm"] == pytest.approx(75000)
    assert all(s["plane_1_moment_nmm"] == 0 for s in canceled["resultant_stations"])


def test_zero_ties_and_proven_plateau():
    zero = result([], [])
    assert zero["critical_resultant_bending_moment_nmm"] == 0
    assert zero["critical_regions"] == [{"x_start_mm": 0, "x_end_mm": 600}]
    assert [s["position_mm"] for s in zero["critical_stations"]] == [0, 600]
    tied = result([(-1000, 100), (2000, 200), (-2000, 400), (1000, 500)], [])
    assert [s["position_mm"] for s in tied["critical_stations"]] == [200, 400]
    plateau = result([(-1000, 200), (-1000, 400)], [])
    assert plateau["critical_regions"] == [{"x_start_mm": 200, "x_end_mm": 400}]


@pytest.mark.parametrize("span,p1,p2", [
    (0, [], []), (-1, [], []), (float("nan"), [], []),
    (600, [PointLoad(1, 601)], []), (600, [], [PointLoad(1, -1)]),
    (600, [PointLoad(float("inf"), 200)], []),
    (600, [], [PointLoad(float("nan"), 200)]),
    (600, "bad", []), (600, [], [{"load_n": 1, "position_mm": 200}]),
    (600, None, []), (True, [], []),
])
def test_invalid_inputs(span, p1, p2):
    with pytest.raises(ValueError):
        calc(span, p1, p2)


def test_reviewer_rejects_different_nested_span():
    value = result([(-1000, 200)], [(-1000, 400)])
    value["plane_2"] = asdict(calc(500, [], []).plane_2)
    assert review_engineering_result(value).status == "FAIL"


@pytest.mark.parametrize("field,mutate", [
    ("nested reaction", lambda v: v["plane_1"].__setitem__("reaction_a_n", 0)),
    ("component", lambda v: v["resultant_stations"][1].__setitem__("plane_2_moment_nmm", 0)),
    ("resultant", lambda v: v["resultant_stations"][1].__setitem__("resultant_bending_moment_nmm", 0)),
    ("critical value", lambda v: v.__setitem__("critical_resultant_bending_moment_nmm", 0)),
    ("critical station", lambda v: v["critical_stations"][0].__setitem__("position_mm", 300)),
    ("critical component", lambda v: v["critical_stations"][0].__setitem__("plane_1_moment_nmm", 0)),
    ("critical region", lambda v: v["critical_regions"][0].__setitem__("x_end_mm", 300)),
    ("common stations", lambda v: v["common_stations_mm"].pop(1)),
    ("wrong separate-maxima rule", lambda v: v.__setitem__(
        "critical_resultant_bending_moment_nmm",
        math.hypot(v["plane_1"]["critical_bending_moment_nmm"],
                   v["plane_2"]["critical_bending_moment_nmm"]))),
])
def test_reviewer_rejects_tampering(field, mutate):
    bad = deepcopy(result([(-1000, 200)], [(-1000, 400)]))
    mutate(bad)
    assert review_engineering_result(bad).status == "FAIL", field


def test_registry_marks_endpoint_rule_as_project_derivation():
    provenance = resolve_model_provenance(MODEL_ID)
    assert [s["id"] for s in provenance["sources"]] == ["engineering_statics_beam_equilibrium"]
    assert "project mathematical derivation" in provenance["model"]["derivation"]
    assert "project implementation rules" in provenance["model"]["derivation"]
