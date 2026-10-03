"""Single-file presentation of an already verified shaft analysis chain."""

import argparse
from dataclasses import asdict, dataclass, is_dataclass
from html import escape
import json
from pathlib import Path
from xml.etree import ElementTree as ET

REPORT_BUILDER_ID = "shaft_analysis_html_report_v1"
TORQUE_MODEL_ID = "transmitted_torque_v1"
STATICS_MODEL_ID = "simply_supported_multi_point_load_v1"
COMBINED_MODEL_ID = "solid_shaft_combined_tresca_v1"
WORKFLOW_ID = "verified_shaft_strength_chain_v1"
RENDERER_ID = "shaft_statics_svg_v1"
SVG_NS = "http://www.w3.org/2000/svg"


@dataclass(frozen=True, slots=True)
class ReportArtifact:
    report_builder_id: str
    output_path: str
    report_format: str
    torque_model_id: str
    statics_model_id: str
    combined_model_id: str
    renderer_id: str
    title: str


def _mapping(value, label):
    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _require(data, key, expected=None):
    if key not in data:
        raise ValueError(f"missing field: {key}")
    value = data[key]
    if expected is not None and value != expected:
        raise ValueError(f"{key} must be {expected}")
    return value


def _svg(path, label):
    path = Path(path)
    if path.suffix.lower() != ".svg" or not path.is_file():
        raise ValueError(f"{label} must be an existing .svg file")
    raw = path.read_bytes()
    if b"<!doctype" in raw.lower() or b"<!entity" in raw.lower():
        raise ValueError(f"{label} contains prohibited XML declarations")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError(f"{label} is invalid SVG: {exc}") from exc
    ns = f"{{{SVG_NS}}}"
    if root.tag != ns + "svg":
        raise ValueError(f"{label} has no SVG root")
    allowed_tags = {"svg", "title", "metadata", "rect", "text", "line", "g"}
    allowed_attrs = {"xmlns", "viewBox", "role", "width", "height", "fill", "x", "y",
                     "font-size", "stroke", "stroke-width", "x1", "x2", "y1", "y2",
                     "text-anchor", "data-role", "data-index", "data-x-start-mm", "data-x-end-mm"}
    for element in root.iter():
        if element.tag not in {ns + tag for tag in allowed_tags}:
            raise ValueError(f"{label} contains an unsupported SVG element")
        if any(attr not in allowed_attrs for attr in element.attrib):
            raise ValueError(f"{label} contains an unsupported SVG attribute")
    metadata = root.find(ns + "metadata")
    try:
        identity = json.loads(metadata.text) if metadata is not None else None
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} has invalid renderer metadata") from exc
    if identity != {"renderer_id": RENDERER_ID, "input_model_id": STATICS_MODEL_ID}:
        raise ValueError(f"{label} has mismatched renderer metadata")
    ET.register_namespace("", SVG_NS)
    return ET.tostring(root, encoding="unicode")


def _provenance(value, model_id):
    result = _mapping(value, "provenance")
    model = _mapping(_require(result, "model"), "provenance model")
    _require(model, "model_id", model_id)
    sources = _require(result, "sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("provenance sources must be a non-empty array")
    if [source.get("id") for source in sources if isinstance(source, dict)] != model.get("source_ids"):
        raise ValueError("provenance sources do not match model source_ids")
    for source in sources:
        _require(_mapping(source, "source"), "title")
        _require(source, "supports")
    return model, sources


def _text(value):
    return escape(str(value), quote=True)


def _display(value):
    return f"{value:.3f}" if isinstance(value, (int, float)) and not isinstance(value, bool) else _text(value)


def _row(name, value):
    return f"<tr><th>{_text(name)}</th><td>{_text(value)}</td></tr>"


def build_shaft_analysis_report(*, torque_result, statics_result, verified_strength_result,
                                torque_provenance, statics_provenance, combined_provenance,
                                diagram_artifacts, output_path) -> ReportArtifact:
    """Validate identities and exact handoff fields, then format existing artifacts."""
    torque = _mapping(torque_result, "torque_result")
    statics = _mapping(statics_result, "statics_result")
    workflow = _mapping(verified_strength_result, "verified_strength_result")
    diagrams = _mapping(diagram_artifacts, "diagram_artifacts")
    _require(torque, "model_id", TORQUE_MODEL_ID)
    _require(statics, "model_id", STATICS_MODEL_ID)
    _require(workflow, "workflow_id", WORKFLOW_ID)
    _require(workflow, "status", "PASS")
    _require(workflow, "torque_model_id", TORQUE_MODEL_ID)
    _require(workflow, "statics_model_id", STATICS_MODEL_ID)
    _require(workflow, "combined_model_id", COMBINED_MODEL_ID)
    for field in ("upstream_torque_review_status", "upstream_statics_review_status",
                  "combined_review_status"):
        _require(workflow, field, "PASS")
    combined = _mapping(_require(workflow, "combined_result"), "combined_result")
    _require(combined, "model_id", COMBINED_MODEL_ID)
    _require(diagrams, "renderer_id", RENDERER_ID)
    _require(diagrams, "input_model_id", STATICS_MODEL_ID)
    for left, right, label in (
        (workflow.get("torque_nm"), torque.get("torque_nm"), "torque lineage"),
        (workflow.get("bending_moment_nm"), statics.get("max_bending_moment_nm"), "moment lineage"),
        (combined.get("torque_nm"), torque.get("torque_nm"), "combined torque lineage"),
        (combined.get("bending_moment_nm"), statics.get("max_bending_moment_nm"), "combined moment lineage"),
        (combined.get("allowable_shear_mpa"), workflow.get("allowable_shear_mpa"), "allowable shear lineage"),
    ):
        if left is None or right is None or left != right:
            raise ValueError(f"{label} mismatch")
    _require(diagrams, "span_mm", _require(statics, "span_mm"))
    cards = [_provenance(value, model_id) for value, model_id in (
        (torque_provenance, TORQUE_MODEL_ID),
        (statics_provenance, STATICS_MODEL_ID),
        (combined_provenance, COMBINED_MODEL_ID),
    )]
    shear_svg = _svg(_require(diagrams, "shear_force_svg"), "shear_force_svg")
    moment_svg = _svg(_require(diagrams, "bending_moment_svg"), "bending_moment_svg")
    loads = _require(statics, "loads")
    regions = _require(statics, "max_moment_regions")
    if not isinstance(loads, list) or not isinstance(regions, list):
        raise ValueError("loads and max_moment_regions must be arrays")
    load_items = "".join(f"<li>{_display(_require(load, 'load_n'))} N @ "
                         f"{_display(_require(load, 'position_mm'))} mm</li>" for load in loads)
    region_items = "; ".join(
        f"{_display(_require(region, 'x_start_mm'))} mm" if region.get("x_start_mm") == region.get("x_end_mm")
        else f"{_display(_require(region, 'x_start_mm'))}–{_display(_require(region, 'x_end_mm'))} mm"
        for region in regions
    )
    assumption_items = "".join(
        f"<h3>{_text(model['title'])}</h3><ul>" + "".join(
            f"<li>{_text(item)}</li>" for item in model.get("assumptions", []) + model.get("limitations", [])
        ) + "</ul>" for model, _ in cards
    )
    source_rows = "".join(
        f"<tr><td>{_text(model['model_id'])}</td><td>{_text(source['title'])}</td>"
        f"<td>{_text('; '.join(source['supports']))}</td></tr>"
        for model, sources in cards for source in sources
    )
    metadata = {
        "report_builder_id": REPORT_BUILDER_ID,
        "torque_model_id": TORQUE_MODEL_ID, "statics_model_id": STATICS_MODEL_ID,
        "combined_model_id": COMBINED_MODEL_ID, "workflow_id": WORKFLOW_ID,
        "renderer_id": RENDERER_ID,
        "torque_nm": _require(torque, "torque_nm"),
        "reaction_a_n": _require(statics, "reaction_a_n"),
        "reaction_b_n": _require(statics, "reaction_b_n"),
        "max_bending_moment_nm": _require(statics, "max_bending_moment_nm"),
        "max_moment_regions": regions,
        "allowable_shear_mpa": _require(workflow, "allowable_shear_mpa"),
        "min_diameter_mm": _require(combined, "min_diameter_mm"),
        "upstream_torque_review_status": workflow["upstream_torque_review_status"],
        "upstream_statics_review_status": workflow["upstream_statics_review_status"],
        "combined_review_status": workflow["combined_review_status"],
        "workflow_status": workflow["status"],
    }
    json_data = json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                           allow_nan=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    title = "Mechanical Shaft Analysis Report"
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>
body{{font:16px/1.55 system-ui,Arial,sans-serif;color:#182b39;background:#fff;max-width:960px;margin:0 auto;padding:2rem}}
h1,h2,h3{{line-height:1.25}}h1{{margin-bottom:.1rem}}h2{{border-bottom:1px solid #b9c8d0;padding-bottom:.3rem;margin-top:2rem}}
.subtitle,.note{{color:#526977}}table{{border-collapse:collapse;width:100%}}th,td{{border-bottom:1px solid #d9e1e6;padding:.55rem;text-align:left;vertical-align:top}}
th{{width:42%}}svg{{width:100%;height:auto}}.diagram{{overflow:auto}}@media print{{body{{max-width:none;padding:0}}h2,.diagram{{break-inside:avoid}}}}
</style></head><body>
<header><h1>{title}</h1><p class="subtitle">Verified deterministic analysis</p></header>
<section><h2>Analysis Summary</h2><p>Complete multi-point shaft workflow: transmitted torque, simply supported statics, and theoretical combined-strength sizing.</p>
<p class="note">Displayed values are presentation-rounded; full deterministic values are included in report metadata.</p></section>
<section><h2>Input Conditions</h2><table>
{_row('Power', str(_display(_require(torque, 'power_kw'))) + ' kW')}
{_row('Speed', str(_display(_require(torque, 'speed_rpm'))) + ' rpm')}
{_row('Span', str(_display(statics['span_mm'])) + ' mm')}
{_row('Allowable shear stress', str(_display(workflow['allowable_shear_mpa'])) + ' MPa')}
</table><h3>Point loads</h3><ul>{load_items}</ul></section>
<section><h2>Verified Engineering Results</h2><table>
{_row('Transmitted torque', str(_display(torque['torque_nm'])) + ' N·m')}
{_row('Reaction A', str(_display(statics['reaction_a_n'])) + ' N')}
{_row('Reaction B', str(_display(statics['reaction_b_n'])) + ' N')}
{_row('Maximum bending moment', str(_display(statics['max_bending_moment_nm'])) + ' N·m')}
{_row('Maximum bending moment region', region_items)}
{_row('Theoretical minimum shaft diameter', str(_display(combined['min_diameter_mm'])) + ' mm')}
</table></section>
<section><h2>Shear Force Diagram</h2><div class="diagram">{shear_svg}</div></section>
<section><h2>Bending Moment Diagram</h2><div class="diagram">{moment_svg}</div></section>
<section><h2>Model and Verification Trace</h2><table>
{_row('Torque model', TORQUE_MODEL_ID + ' — PASS')}
{_row('Statics model', STATICS_MODEL_ID + ' — PASS')}
{_row('Combined-strength model', COMBINED_MODEL_ID + ' — PASS')}
{_row('Cross-calculator handoff', WORKFLOW_ID + ' — PASS')}
{_row('Diagram renderer', RENDERER_ID)}
</table></section>
<section><h2>Assumptions and Limitations</h2>{assumption_items}
<p>The reported diameter is a theoretical minimum under the implemented model, not a final production shaft diameter.</p></section>
<section><h2>Sources / Provenance</h2><table><thead><tr><th>Model</th><th>Source title</th><th>Relevant relationship / support</th></tr></thead><tbody>{source_rows}</tbody></table></section>
<section><h2>Machine-readable Metadata</h2><p>Full precision deterministic values.</p>
<script type="application/json" id="engineering-report-data">{json_data}</script></section>
</body></html>
"""
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(html.encode("utf-8"))
    return ReportArtifact(REPORT_BUILDER_ID, str(target), "html", TORQUE_MODEL_ID,
                          STATICS_MODEL_ID, COMBINED_MODEL_ID, RENDERER_ID, title)


def main():
    parser = argparse.ArgumentParser(description="Build a verified single-file shaft analysis HTML report")
    parser.add_argument("--input-manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    manifest_path = Path(args.input_manifest)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        keys = ("torque_result", "statics_result", "verified_strength_result",
                "torque_provenance", "statics_provenance", "combined_provenance", "diagram_artifacts")
        inputs = {}
        for key in keys:
            path = Path(manifest[key])
            if not path.is_absolute():
                path = manifest_path.parent / path
            inputs[key] = json.loads(path.read_text(encoding="utf-8"))
            if key == "diagram_artifacts":
                for diagram_key in ("shear_force_svg", "bending_moment_svg"):
                    svg_path = Path(inputs[key][diagram_key])
                    if not svg_path.is_absolute():
                        inputs[key][diagram_key] = str(path.parent / svg_path)
        artifact = build_shaft_analysis_report(**inputs, output_path=args.output)
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(asdict(artifact), ensure_ascii=False))


if __name__ == "__main__":
    main()
