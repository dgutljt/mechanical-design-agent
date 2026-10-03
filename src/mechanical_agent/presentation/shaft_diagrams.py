"""Deterministic SVG diagrams from multi-point shaft statics segment data."""

import argparse
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import sys
from typing import Any
from xml.etree import ElementTree as ET

from mechanical_agent.calculators.shaft_statics_multi import (
    MODEL_ID as INPUT_MODEL_ID,
    MomentRegion,
    MultiLoadStaticsResult,
    PointLoad,
    StaticsSegment,
)

RENDERER_ID = "shaft_statics_svg_v1"
SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)

WIDTH, HEIGHT = 1200, 500
LEFT, RIGHT = 120.0, 1080.0
TOP, BOTTOM = 150.0, 370.0


@dataclass(frozen=True)
class DiagramArtifacts:
    renderer_id: str
    input_model_id: str
    shear_force_svg: str
    bending_moment_svg: str
    span_mm: float
    shear_unit: str
    moment_unit: str


def _number(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    return number


def _format_number(value: float) -> str:
    """Use Python's shortest round-trip decimal representation for display."""
    return str(value)


def _field(data: dict[str, Any], name: str) -> Any:
    if name not in data:
        raise ValueError(f"missing field: {name}")
    return data[name]


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _items(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be an array")
    return value


def result_from_mapping(data: Any) -> MultiLoadStaticsResult:
    """Parse the calculator JSON fields used for presentation into typed data."""
    obj = _object(data, "input")
    model_id = _field(obj, "model_id")
    if model_id != INPUT_MODEL_ID:
        raise ValueError(f"unsupported diagram input model: {model_id}")
    loads = []
    for index, raw in enumerate(_items(_field(obj, "loads"), "loads")):
        item = _object(raw, f"loads[{index}]")
        loads.append(PointLoad(
            _number(f"loads[{index}].load_n", _field(item, "load_n")),
            _number(f"loads[{index}].position_mm", _field(item, "position_mm")),
        ))
    segments = []
    for index, raw in enumerate(_items(_field(obj, "segments"), "segments")):
        item = _object(raw, f"segments[{index}]")
        segments.append(StaticsSegment(*(
            _number(f"segments[{index}].{name}", _field(item, name))
            for name in ("x_start_mm", "x_end_mm", "shear_n", "moment_start_nmm", "moment_end_nmm")
        )))
    regions = []
    for index, raw in enumerate(_items(_field(obj, "max_moment_regions"), "max_moment_regions")):
        item = _object(raw, f"max_moment_regions[{index}]")
        regions.append(MomentRegion(
            _number(f"max_moment_regions[{index}].x_start_mm", _field(item, "x_start_mm")),
            _number(f"max_moment_regions[{index}].x_end_mm", _field(item, "x_end_mm")),
        ))
    result = MultiLoadStaticsResult(
        model_id=model_id,
        span_mm=_number("span_mm", _field(obj, "span_mm")),
        loads=loads,
        total_load_n=_number("total_load_n", _field(obj, "total_load_n")),
        reaction_a_n=_number("reaction_a_n", _field(obj, "reaction_a_n")),
        reaction_b_n=_number("reaction_b_n", _field(obj, "reaction_b_n")),
        segments=segments,
        max_bending_moment_nmm=_number("max_bending_moment_nmm", _field(obj, "max_bending_moment_nmm")),
        max_bending_moment_nm=_number("max_bending_moment_nm", _field(obj, "max_bending_moment_nm")),
        max_moment_regions=regions,
        formula=_field(obj, "formula"),
        assumptions=_field(obj, "assumptions"),
    )
    _validate_result(result)
    return result


def _validate_result(result: MultiLoadStaticsResult) -> None:
    if not isinstance(result, MultiLoadStaticsResult):
        raise ValueError("result must be a MultiLoadStaticsResult")
    if result.model_id != INPUT_MODEL_ID:
        raise ValueError(f"unsupported diagram input model: {result.model_id}")
    span = _number("span_mm", result.span_mm)
    if span <= 0:
        raise ValueError("span_mm must be greater than 0")
    for name in ("reaction_a_n", "reaction_b_n", "max_bending_moment_nmm", "max_bending_moment_nm"):
        _number(name, getattr(result, name))
    if not isinstance(result.loads, list):
        raise ValueError("loads must be an array")
    for index, load in enumerate(result.loads):
        if not isinstance(load, PointLoad):
            raise ValueError(f"loads[{index}] must be a PointLoad")
        _number(f"loads[{index}].load_n", load.load_n)
        position = _number(f"loads[{index}].position_mm", load.position_mm)
        if not 0 <= position <= span:
            raise ValueError(f"loads[{index}].position_mm must be within span")
    if not isinstance(result.segments, list) or not result.segments:
        raise ValueError("segments must be a non-empty array")
    previous_end = 0.0
    for index, segment in enumerate(result.segments):
        if not isinstance(segment, StaticsSegment):
            raise ValueError(f"segments[{index}] must be a StaticsSegment")
        start = _number(f"segments[{index}].x_start_mm", segment.x_start_mm)
        end = _number(f"segments[{index}].x_end_mm", segment.x_end_mm)
        for name in ("shear_n", "moment_start_nmm", "moment_end_nmm"):
            _number(f"segments[{index}].{name}", getattr(segment, name))
        if start != previous_end or not start < end or end > span:
            raise ValueError("segments must be ordered, contiguous, and within span")
        previous_end = end
    if previous_end != span:
        raise ValueError("segments must end at span_mm")
    if not isinstance(result.max_moment_regions, list):
        raise ValueError("max_moment_regions must be an array")
    for index, region in enumerate(result.max_moment_regions):
        if not isinstance(region, MomentRegion):
            raise ValueError(f"max_moment_regions[{index}] must be a MomentRegion")
        start = _number(f"max_moment_regions[{index}].x_start_mm", region.x_start_mm)
        end = _number(f"max_moment_regions[{index}].x_end_mm", region.x_end_mm)
        if not 0 <= start <= end <= span:
            raise ValueError("max_moment_regions must be within span")


def _x(position: float, span: float) -> float:
    return LEFT + position / span * (RIGHT - LEFT)


def _svg_text(parent: ET.Element, x: float, y: float, content: str, **attrs: str) -> None:
    ET.SubElement(parent, "text", {"x": _format_number(x), "y": _format_number(y), **attrs}).text = content


def _line(parent: ET.Element, x1: float, y1: float, x2: float, y2: float, **attrs: str) -> None:
    ET.SubElement(parent, "line", {
        "x1": _format_number(x1), "y1": _format_number(y1),
        "x2": _format_number(x2), "y2": _format_number(y2), **attrs,
    })


def _base(result: MultiLoadStaticsResult, title: str, ylabel: str) -> tuple[ET.Element, ET.Element]:
    root = ET.Element("svg", {"xmlns": SVG_NS, "viewBox": f"0 0 {WIDTH} {HEIGHT}", "role": "img"})
    ET.SubElement(root, "title").text = title
    ET.SubElement(root, "metadata").text = json.dumps(
        {"renderer_id": RENDERER_ID, "input_model_id": result.model_id}, sort_keys=True
    )
    ET.SubElement(root, "rect", {"width": str(WIDTH), "height": str(HEIGHT), "fill": "white"})
    _svg_text(root, 40, 38, title, fill="#172a3a", **{"font-size": "26"})
    _svg_text(root, 40, 70, f"Span: {_format_number(result.span_mm)} mm", **{"font-size": "15"})
    _svg_text(root, 40, 96, f"RA: {_format_number(result.reaction_a_n)} N   RB: {_format_number(result.reaction_b_n)} N", **{"font-size": "15"})
    _svg_text(root, 40, 122, "Loads: " + ("; ".join(
        f"{_format_number(load.load_n)} N @ {_format_number(load.position_mm)} mm"
        for load in result.loads
    ) or "none"), **{"font-size": "13"})
    _line(root, LEFT, BOTTOM, RIGHT, BOTTOM, stroke="#586a78", **{"stroke-width": "1"})
    _line(root, LEFT, TOP, LEFT, BOTTOM, stroke="#586a78", **{"stroke-width": "1"})
    _svg_text(root, 520, 485, "Position x (mm)", **{"font-size": "16"})
    _svg_text(root, 20, 270, ylabel, **{"font-size": "16"})
    _svg_text(root, LEFT, 425, "0 mm", **{"font-size": "13"})
    _svg_text(root, RIGHT, 425, f"{_format_number(result.span_mm)} mm", **{"font-size": "13", "text-anchor": "end"})
    _svg_text(root, LEFT, 450, "Support A", **{"font-size": "14"})
    _svg_text(root, RIGHT, 450, "Support B", **{"font-size": "14", "text-anchor": "end"})
    return root, ET.SubElement(root, "g", {"stroke": "#146b85", "stroke-width": "3", "fill": "none"})


def _shear_svg(result: MultiLoadStaticsResult) -> bytes:
    root, plot = _base(result, "Shear Force Diagram", "Shear V (N)")
    maximum = max(abs(segment.shear_n) for segment in result.segments)
    zero = (TOP + BOTTOM) / 2
    scale = (BOTTOM - TOP) * 0.42 / (maximum or 1.0)
    _line(root, LEFT, zero, RIGHT, zero, stroke="#a9b5bd", **{"stroke-width": "1"})
    _svg_text(root, RIGHT, TOP + 10, f"+{_format_number(maximum)} N", **{"text-anchor": "end"})
    _svg_text(root, RIGHT, BOTTOM - 4, f"-{_format_number(maximum)} N", **{"text-anchor": "end"})
    previous_y = zero
    for index, segment in enumerate(result.segments):
        x1, x2 = _x(segment.x_start_mm, result.span_mm), _x(segment.x_end_mm, result.span_mm)
        y = zero - segment.shear_n * scale
        _line(plot, x1, previous_y, x1, y, **{"data-role": "shear-jump"})
        _line(plot, x1, y, x2, y, **{
            "data-role": "shear-segment", "data-index": str(index),
            "data-x-start-mm": _format_number(segment.x_start_mm),
            "data-x-end-mm": _format_number(segment.x_end_mm),
        })
        previous_y = y
    _line(plot, RIGHT, previous_y, RIGHT, zero, **{"data-role": "shear-jump"})
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _moment_svg(result: MultiLoadStaticsResult) -> bytes:
    root, plot = _base(result, "Bending Moment Diagram", "Bending Moment M (N·m)")
    values = [value for segment in result.segments
              for value in (segment.moment_start_nmm, segment.moment_end_nmm)]
    low, high = min(0.0, *values), max(0.0, *values)
    extent = high - low or 1.0
    def y(value: float) -> float:
        return BOTTOM - (value - low) / extent * (BOTTOM - TOP) * 0.82
    _line(root, LEFT, y(0.0), RIGHT, y(0.0), stroke="#a9b5bd", **{"stroke-width": "1"})
    for index, segment in enumerate(result.segments):
        _line(plot, _x(segment.x_start_mm, result.span_mm), y(segment.moment_start_nmm),
              _x(segment.x_end_mm, result.span_mm), y(segment.moment_end_nmm), **{
                  "data-role": "moment-segment", "data-index": str(index),
                  "data-x-start-mm": _format_number(segment.x_start_mm),
                  "data-x-end-mm": _format_number(segment.x_end_mm),
              })
    _svg_text(root, 700, 70, f"Mmax: {_format_number(result.max_bending_moment_nm)} N·m",
              **{"font-size": "16"})
    for index, region in enumerate(result.max_moment_regions):
        start, end = _format_number(region.x_start_mm), _format_number(region.x_end_mm)
        label = (f"Maximum moment at x = {start} mm" if region.x_start_mm == region.x_end_mm
                 else f"Maximum moment from x = {start} mm to x = {end} mm")
        _svg_text(root, 700, 96 + index * 20, label, **{"font-size": "14"})
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def render_shaft_statics_diagrams(result: MultiLoadStaticsResult, output_dir: str | Path) -> DiagramArtifacts:
    """Render existing statics values to SVG without engineering arithmetic."""
    _validate_result(result)
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    shear_path = directory / "shear_force_diagram.svg"
    moment_path = directory / "bending_moment_diagram.svg"
    shear_path.write_bytes(_shear_svg(result))
    moment_path.write_bytes(_moment_svg(result))
    return DiagramArtifacts(RENDERER_ID, result.model_id, str(shear_path), str(moment_path),
                            result.span_mm, "N", "N·m")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render multi-point shaft statics JSON to SVG diagrams.")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    try:
        result = result_from_mapping(json.load(sys.stdin))
        artifacts = render_shaft_statics_diagrams(result, args.output_dir)
    except (ValueError, TypeError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(asdict(artifacts), allow_nan=False))


if __name__ == "__main__":
    main()
