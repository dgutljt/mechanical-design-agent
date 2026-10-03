import copy
from dataclasses import asdict, replace
from html.parser import HTMLParser
import json
from pathlib import Path

import pytest

from mechanical_agent.calculators.torque import calculate_transmitted_torque
from mechanical_agent.calculators.shaft_statics_multi import PointLoad, calculate_simply_supported_point_loads
from mechanical_agent.calculators.shaft_statics import calculate_simply_supported_point_load
from mechanical_agent.knowledge_registry import resolve_model_provenance
from mechanical_agent.presentation.shaft_diagrams import render_shaft_statics_diagrams
from mechanical_agent.reporting.shaft_analysis_report import (
    REPORT_BUILDER_ID, build_shaft_analysis_report,
)
from mechanical_agent.workflows.verified_shaft_strength import run_verified_shaft_strength_chain


class ReportParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.headings = []
        self.metadata = ""
        self._heading = False
        self._metadata = False
        self.svgs = 0

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        self._heading = tag in ("h1", "h2")
        self._metadata = tag == "script" and attributes.get("id") == "engineering-report-data"
        if tag == "svg":
            self.svgs += 1

    def handle_endtag(self, tag):
        if tag in ("h1", "h2"):
            self._heading = False
        if tag == "script":
            self._metadata = False

    def handle_data(self, data):
        if self._heading:
            self.headings.append(data)
        if self._metadata:
            self.metadata += data


@pytest.fixture
def inputs(tmp_path):
    torque = asdict(calculate_transmitted_torque(5.5, 960))
    statics_object = calculate_simply_supported_point_loads(
        600, [PointLoad(1000, 200), PointLoad(500, 450)])
    statics = asdict(statics_object)
    workflow = run_verified_shaft_strength_chain(torque, statics, 40)
    diagrams = render_shaft_statics_diagrams(statics_object, tmp_path / "diagrams")
    return dict(
        torque_result=torque, statics_result=statics, verified_strength_result=workflow,
        torque_provenance=resolve_model_provenance(torque["model_id"]),
        statics_provenance=resolve_model_provenance(statics["model_id"]),
        combined_provenance=resolve_model_provenance(workflow.combined_result["model_id"]),
        diagram_artifacts=diagrams,
    )


def build(inputs, path):
    return build_shaft_analysis_report(**inputs, output_path=path)


def test_happy_path_structure_precision_and_provenance(inputs, tmp_path):
    output = tmp_path / "report.html"
    artifact = build(inputs, output)
    assert artifact.report_builder_id == REPORT_BUILDER_ID
    assert artifact.report_format == "html"
    assert artifact.output_path == str(output)
    html = output.read_text(encoding="utf-8")
    parsed = ReportParser()
    parsed.feed(html)
    assert set(("Mechanical Shaft Analysis Report", "Analysis Summary", "Input Conditions",
                "Verified Engineering Results", "Shear Force Diagram", "Bending Moment Diagram",
                "Model and Verification Trace", "Assumptions and Limitations",
                "Sources / Provenance", "Machine-readable Metadata")) <= set(parsed.headings)
    assert parsed.svgs == 2
    data = json.loads(parsed.metadata)
    assert data["torque_nm"] == 54.713541666666664
    assert data["max_bending_moment_nm"] == 158.33333333333334
    assert data["min_diameter_mm"] == 27.732717671613003
    assert "54.714 N·m" in html and "27.733 mm" in html
    assert "presentation-rounded" in html
    titles = [source["title"] for key in ("torque_provenance", "statics_provenance",
                                              "combined_provenance") for source in inputs[key]["sources"]]
    assert all(title in html for title in titles)
    assert "file:///" not in html and "C:\\Users\\" not in html
    assert "https://" not in html and "<script type=\"text/javascript\"" not in html


def test_deterministic_bytes(inputs, tmp_path):
    first, second = tmp_path / "first.html", tmp_path / "second.html"
    build(inputs, first)
    build(inputs, second)
    assert first.read_bytes() == second.read_bytes()


@pytest.mark.parametrize("field", ["torque_nm", "bending_moment_nm"])
def test_lineage_tamper_rejected_without_file(inputs, tmp_path, field):
    inputs["verified_strength_result"] = replace(inputs["verified_strength_result"], **{field: 999})
    output = tmp_path / "bad.html"
    with pytest.raises(ValueError, match="lineage mismatch"):
        build(inputs, output)
    assert not output.exists()


@pytest.mark.parametrize("field", ["upstream_torque_review_status", "upstream_statics_review_status",
                                    "combined_review_status"])
def test_review_tamper_rejected(inputs, tmp_path, field):
    inputs["verified_strength_result"] = replace(inputs["verified_strength_result"], **{field: "FAIL"})
    output = tmp_path / "bad.html"
    with pytest.raises(ValueError, match=field):
        build(inputs, output)
    assert not output.exists()


def test_wrong_model_rejected(inputs, tmp_path):
    inputs["statics_result"] = asdict(calculate_simply_supported_point_load(1000, 600, 200))
    with pytest.raises(ValueError, match="model_id"):
        build(inputs, tmp_path / "bad.html")


def test_missing_svg_rejected(inputs, tmp_path):
    inputs["diagram_artifacts"] = replace(inputs["diagram_artifacts"],
        shear_force_svg=str(tmp_path / "missing.svg"))
    with pytest.raises(ValueError, match="existing .svg"):
        build(inputs, tmp_path / "bad.html")


def test_malicious_svg_rejected(inputs, tmp_path):
    path = tmp_path / "malicious.svg"
    path.write_text('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', encoding="utf-8")
    inputs["diagram_artifacts"] = replace(inputs["diagram_artifacts"], shear_force_svg=str(path))
    output = tmp_path / "bad.html"
    with pytest.raises(ValueError, match="unsupported SVG element"):
        build(inputs, output)
    assert not output.exists()


def test_provenance_uses_only_resolver_output_and_escapes(inputs, tmp_path):
    inputs["torque_provenance"] = copy.deepcopy(inputs["torque_provenance"])
    inputs["torque_provenance"]["sources"][0]["title"] = '<img src=x onerror=alert(1)>'
    html_path = tmp_path / "escaped.html"
    build(inputs, html_path)
    html = html_path.read_text(encoding="utf-8")
    assert "&lt;img src=x onerror=alert(1)&gt;" in html
    assert "<img src=x" not in html
