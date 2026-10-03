import json
import math
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from mechanical_agent.calculators.shaft_statics_multi import (
    PointLoad, calculate_simply_supported_point_loads,
)
from mechanical_agent.presentation.shaft_diagrams import (
    RENDERER_ID, _format_number, render_shaft_statics_diagrams,
)


MODULE = "mechanical_agent.presentation.shaft_diagrams"
NS = "{http://www.w3.org/2000/svg}"


def _render(tmp_path, loads):
    result = calculate_simply_supported_point_loads(600, loads)
    artifacts = render_shaft_statics_diagrams(result, tmp_path)
    roots = [ET.parse(path).getroot() for path in
             (artifacts.shear_force_svg, artifacts.bending_moment_svg)]
    return result, artifacts, roots


def _lines(root, role):
    return [element for element in root.iter(f"{NS}line")
            if element.get("data-role") == role]


def test_case_a_svg_metadata_labels_and_geometry(tmp_path):
    result, artifacts, (shear, moment) = _render(
        tmp_path, [PointLoad(1000, 200), PointLoad(500, 450)])
    assert artifacts.renderer_id == RENDERER_ID
    assert artifacts.input_model_id == result.model_id
    assert artifacts.span_mm == 600
    assert artifacts.shear_unit == "N"
    assert artifacts.moment_unit == "N·m"
    for root, path, title in ((shear, artifacts.shear_force_svg, "Shear Force Diagram"),
                              (moment, artifacts.bending_moment_svg, "Bending Moment Diagram")):
        assert root.tag == f"{NS}svg"
        assert root.get("viewBox") == "0 0 1200 500"
        metadata = json.loads(root.find(f"{NS}metadata").text)
        assert metadata == {"renderer_id": RENDERER_ID, "input_model_id": result.model_id}
        content = Path(path).read_text(encoding="utf-8")
        assert title in content
        assert "Position x (mm)" in content
        assert "Support A" in content and "Support B" in content
        assert "nan" not in content.lower() and "infinity" not in content.lower()
        assert "C:\\Users\\" not in content and "/Users/" not in content
    assert "Shear V (N)" in Path(artifacts.shear_force_svg).read_text(encoding="utf-8")
    moment_text = Path(artifacts.bending_moment_svg).read_text(encoding="utf-8")
    assert "Bending Moment M (N·m)" in moment_text
    assert f"Mmax: {result.max_bending_moment_nm} N·m" in moment_text
    assert "Maximum moment at x = 200.0 mm" in moment_text
    shear_segments = _lines(shear, "shear-segment")
    assert len(shear_segments) == 3
    assert [line.get("data-x-start-mm") for line in shear_segments] == ["0.0", "200.0", "450.0"]
    moment_segments = _lines(moment, "moment-segment")
    assert [(line.get("data-x-start-mm"), line.get("data-x-end-mm"))
            for line in moment_segments] == [("0.0", "200.0"), ("200.0", "450.0"), ("450.0", "600.0")]
    x_nodes = [float(moment_segments[0].get("x1"))] + [float(line.get("x2")) for line in moment_segments]
    assert x_nodes == sorted(x_nodes)
    assert len(set(x_nodes)) == 4
    assert x_nodes[0] == 120 and x_nodes[-1] == 1080


def test_plateau_is_horizontal(tmp_path):
    result, artifacts, (_, moment) = _render(
        tmp_path, [PointLoad(1000, 150), PointLoad(1000, 450)])
    plateau = next(line for line in _lines(moment, "moment-segment")
                   if line.get("data-x-start-mm") == "150.0")
    assert plateau.get("data-x-end-mm") == "450.0"
    assert plateau.get("y1") == plateau.get("y2")
    content = Path(artifacts.bending_moment_svg).read_text(encoding="utf-8")
    assert "Maximum moment from x = 150.0 mm to x = 450.0 mm" in content
    assert f"Mmax: {result.max_bending_moment_nm} N·m" in content


@pytest.mark.parametrize("loads", [
    [PointLoad(0, 100)],
    [PointLoad(0, 100), PointLoad(0, 300)],
    [PointLoad(400, 200), PointLoad(600, 200)],
    [PointLoad(500, 0), PointLoad(1000, 200), PointLoad(300, 600)],
])
def test_edge_cases_generate_finite_svg(tmp_path, loads):
    _, artifacts, roots = _render(tmp_path, loads)
    for path, root in zip((artifacts.shear_force_svg, artifacts.bending_moment_svg), roots):
        assert root.tag == f"{NS}svg"
        for line in root.iter(f"{NS}line"):
            for key in ("x1", "x2", "y1", "y2"):
                assert math.isfinite(float(line.get(key)))
        assert Path(path).stat().st_size > 0
    if all(load.load_n == 0 for load in loads):
        shear_text = Path(artifacts.shear_force_svg).read_text(encoding="utf-8")
        assert "+0.0 N" in shear_text and "-0.0 N" in shear_text
        assert "+1.0 N" not in shear_text


def test_deterministic_bytes_and_number_format(tmp_path):
    result = calculate_simply_supported_point_loads(600, [PointLoad(1000, 200), PointLoad(500, 450)])
    first = render_shaft_statics_diagrams(result, tmp_path / "one")
    second = render_shaft_statics_diagrams(result, tmp_path / "two")
    assert Path(first.shear_force_svg).read_bytes() == Path(second.shear_force_svg).read_bytes()
    assert Path(first.bending_moment_svg).read_bytes() == Path(second.bending_moment_svg).read_bytes()
    assert _format_number(result.max_bending_moment_nm) == str(result.max_bending_moment_nm)


def test_cli_manifest_and_errors(tmp_path):
    result = calculate_simply_supported_point_loads(600, [PointLoad(1000, 200), PointLoad(500, 450)])
    payload = asdict(result)
    def run(input_text):
        return subprocess.run([sys.executable, "-m", MODULE, "--output-dir", str(tmp_path / "cli")],
                              input=input_text, text=True, capture_output=True)
    good = run(json.dumps(payload))
    assert good.returncode == 0 and good.stderr == ""
    manifest = json.loads(good.stdout)
    assert set(manifest) == {"renderer_id", "input_model_id", "shear_force_svg",
                             "bending_moment_svg", "span_mm", "shear_unit", "moment_unit"}
    assert all(Path(manifest[key]).is_file() for key in ("shear_force_svg", "bending_moment_svg"))
    for invalid, error in (("{", "Expecting property name"),
                           (json.dumps({**payload, "model_id": "simply_supported_point_load_v1"}),
                            "unsupported diagram input model"),
                           (json.dumps({key: value for key, value in payload.items() if key != "segments"}),
                            "missing field: segments")):
        bad = run(invalid)
        assert bad.returncode == 2 and bad.stdout == ""
        assert error in bad.stderr and "Traceback" not in bad.stderr
