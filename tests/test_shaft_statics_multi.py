import json
import math
import subprocess
import sys
from dataclasses import asdict

import pytest

from mechanical_agent.calculators.shaft_statics import calculate_simply_supported_point_load
from mechanical_agent.calculators.shaft_statics_multi import (
    MomentRegion,
    PointLoad,
    calculate_simply_supported_point_loads,
)


CLOSE = {"rel_tol": 1e-12, "abs_tol": 1e-9}
MODULE = "mechanical_agent.calculators.shaft_statics_multi"


@pytest.mark.parametrize("loads, reactions, moments, peak, regions", [
    ([PointLoad(1000, 200), PointLoad(500, 450)],
     (791.6666666666666, 708.3333333333334),
     (0, 158333.3333333333, 106250, 0), 158333.3333333333,
     [MomentRegion(200, 200)]),
    ([PointLoad(1000, 150), PointLoad(1000, 450)],
     (1000, 1000), (0, 150000, 150000, 0), 150000,
     [MomentRegion(150, 450)]),
    ([PointLoad(1000, 100), PointLoad(500, 300), PointLoad(800, 500)],
     (1216.6666666666667, 1083.3333333333333),
     (0, 121666.66666666667, 165000, 108333.33333333337, 0), 165000,
     [MomentRegion(300, 300)]),
])
def test_reference_cases_and_consistency(loads, reactions, moments, peak, regions):
    result = calculate_simply_supported_point_loads(600, loads)
    assert math.isclose(result.reaction_a_n, reactions[0], **CLOSE)
    assert math.isclose(result.reaction_b_n, reactions[1], **CLOSE)
    assert math.isclose(result.max_bending_moment_nmm, peak, **CLOSE)
    assert math.isclose(result.max_bending_moment_nm, peak / 1000, **CLOSE)
    assert result.max_moment_regions == regions
    assert [s.x_start_mm for s in result.segments] + [600] == sorted(
        {0, 600, *(load.position_mm for load in loads)}
    )
    assert math.isclose(result.segments[0].moment_start_nmm, 0, **CLOSE)
    assert math.isclose(result.segments[-1].moment_end_nmm, 0, **CLOSE)
    for segment, expected in zip(result.segments, moments[1:]):
        assert math.isclose(segment.moment_end_nmm, expected, **CLOSE)
        assert math.isclose(segment.moment_end_nmm,
                            segment.moment_start_nmm + segment.shear_n *
                            (segment.x_end_mm - segment.x_start_mm), **CLOSE)
    for left, right in zip(result.segments, result.segments[1:]):
        assert math.isclose(left.moment_end_nmm, right.moment_start_nmm, **CLOSE)
    assert math.isclose(result.reaction_a_n + result.reaction_b_n,
                        sum(load.load_n for load in loads), **CLOSE)
    assert math.isclose(result.reaction_b_n * 600,
                        sum(load.load_n * load.position_mm for load in loads), **CLOSE)
    assert math.isclose(result.reaction_a_n * 600,
                        sum(load.load_n * (600 - load.position_mm) for load in loads),
                        **CLOSE)
    assert json.loads(json.dumps(asdict(result), allow_nan=False)) == asdict(result)


def test_case_a_shear_and_unsorted_input():
    ordered = [PointLoad(1000, 200), PointLoad(500, 450)]
    reverse = list(reversed(ordered))
    result = calculate_simply_supported_point_loads(600, reverse)
    assert result == calculate_simply_supported_point_loads(600, ordered)
    assert reverse == list(reversed(ordered))
    for actual, expected in zip(
        [segment.shear_n for segment in result.segments],
        [791.6666666666666, -208.33333333333337, -708.3333333333334],
    ):
        assert math.isclose(actual, expected, **CLOSE)
    assert result.loads == ordered


def test_single_load_cross_validation():
    old = calculate_simply_supported_point_load(1000, 400, 150)
    new = calculate_simply_supported_point_loads(400, [PointLoad(1000, 150)])
    for field in ("reaction_a_n", "reaction_b_n", "max_bending_moment_nmm",
                  "max_bending_moment_nm"):
        assert math.isclose(getattr(new, field), getattr(old, field), **CLOSE)
    assert new.max_moment_regions == [MomentRegion(old.max_moment_position_mm,
                                                    old.max_moment_position_mm)]


def test_duplicate_position_and_support_loads():
    split = calculate_simply_supported_point_loads(
        400, [PointLoad(400, 200), PointLoad(600, 200)]
    )
    combined = calculate_simply_supported_point_loads(400, [PointLoad(1000, 200)])
    assert len(split.loads) == 2
    assert split.segments == combined.segments
    assert split.max_moment_regions == combined.max_moment_regions
    supports = calculate_simply_supported_point_loads(
        400, [PointLoad(500, 0), PointLoad(1000, 200), PointLoad(300, 400)]
    )
    assert supports.reaction_a_n == 1000
    assert supports.reaction_b_n == 800
    assert supports.segments[0].shear_n == 500
    assert supports.max_bending_moment_nmm == 100000
    assert supports.max_moment_regions == [MomentRegion(200, 200)]
    assert math.isclose(supports.segments[0].moment_start_nmm, 0, **CLOSE)
    assert math.isclose(supports.segments[-1].moment_end_nmm, 0, **CLOSE)


@pytest.mark.parametrize("loads, region", [
    ([PointLoad(0, 100)], MomentRegion(0, 400)),
    ([PointLoad(500, 0), PointLoad(300, 400)], MomentRegion(0, 400)),
])
def test_zero_internal_moment_plateau(loads, region):
    result = calculate_simply_supported_point_loads(400, loads)
    assert result.max_bending_moment_nmm == 0
    assert result.max_moment_regions == [region]


def test_tiny_positive_load_has_a_point_peak():
    result = calculate_simply_supported_point_loads(400, [PointLoad(1e-12, 200)])
    assert result.max_bending_moment_nmm > 0
    assert result.max_moment_regions == [MomentRegion(200, 200)]


@pytest.mark.parametrize("span, loads, message", [
    (0, [PointLoad(1, 0)], "span_mm must be greater than 0"),
    (-1, [PointLoad(1, 0)], "span_mm must be greater than 0"),
    (math.nan, [PointLoad(1, 0)], "span_mm must be finite"),
    (400, [], "non-empty sequence"),
    (400, {"load_n": 1}, "non-empty sequence"),
    (400, "100@200", "non-empty sequence"),
    (400, [object()], "must be a PointLoad"),
    (400, [PointLoad(-1, 100)], "non-negative"),
    (400, [PointLoad(1, -1)], "between 0 and span_mm"),
    (400, [PointLoad(1, 401)], "between 0 and span_mm"),
    (400, [PointLoad(math.inf, 100)], "must be finite"),
    (400, [PointLoad(1, math.nan)], "must be finite"),
])
def test_invalid_inputs(span, loads, message):
    with pytest.raises(ValueError, match=message):
        calculate_simply_supported_point_loads(span, loads)


def test_cli_json_and_clean_format_error():
    good = subprocess.run(
        [sys.executable, "-m", MODULE, "--span-mm", "600", "--load", "1000@200",
         "--load", "500@450"], capture_output=True, text=True, check=True,
    )
    data = json.loads(good.stdout)
    assert data["loads"] == [{"load_n": 1000, "position_mm": 200},
                              {"load_n": 500, "position_mm": 450}]
    assert len(data["segments"]) == 3
    assert data["max_moment_regions"] == [{"x_start_mm": 200,
                                            "x_end_mm": 200}]
    assert good.stderr == ""
    bad = subprocess.run(
        [sys.executable, "-m", MODULE, "--span-mm", "600", "--load", "bad"],
        capture_output=True, text=True,
    )
    assert bad.returncode != 0
    assert bad.stdout == ""
    assert "--load must have format" in bad.stderr
    assert "Traceback" not in bad.stderr
