"""Verified handoff from reviewed torque and multi-load statics to shaft sizing."""

import argparse
from dataclasses import asdict, dataclass, field
import json
import math
import sys

from mechanical_agent.calculators.shaft_combined import (
    calculate_solid_shaft_min_diameter_combined,
)
from mechanical_agent.review.engineering_result import review_engineering_result

WORKFLOW_ID = "verified_shaft_strength_chain_v1"
TORQUE_MODEL_ID = "transmitted_torque_v1"
STATICS_MODEL_ID = "simply_supported_multi_point_load_v1"
COMBINED_MODEL_ID = "solid_shaft_combined_tresca_v1"


@dataclass(slots=True)
class VerifiedShaftStrengthResult:
    workflow_id: str = WORKFLOW_ID
    status: str = "FAIL"
    torque_model_id: str | None = None
    statics_model_id: str | None = None
    combined_model_id: str = COMBINED_MODEL_ID
    torque_source_field: str = "torque_nm"
    bending_moment_source_field: str = "max_bending_moment_nm"
    torque_nm: float | None = None
    bending_moment_nm: float | None = None
    allowable_shear_mpa: float | None = None
    upstream_torque_review_status: str = "NOT_RUN"
    upstream_statics_review_status: str = "NOT_RUN"
    combined_result: dict | None = None
    combined_review_status: str = "NOT_RUN"
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def run_verified_shaft_strength_chain(
    torque_result: dict,
    statics_result: dict,
    allowable_shear_mpa: float,
) -> VerifiedShaftStrengthResult:
    """Review raw upstream mappings, transfer exact fields, calculate, then review."""
    result = VerifiedShaftStrengthResult(allowable_shear_mpa=allowable_shear_mpa)
    if not isinstance(torque_result, dict) or not isinstance(statics_result, dict):
        result.errors.append("torque_result and statics_result must be JSON objects")
        return result

    result.torque_model_id = torque_result.get("model_id")
    result.statics_model_id = statics_result.get("model_id")
    if result.torque_model_id != TORQUE_MODEL_ID:
        result.errors.append(f"torque model_id must be {TORQUE_MODEL_ID}")
    if result.statics_model_id != STATICS_MODEL_ID:
        result.errors.append(f"statics model_id must be {STATICS_MODEL_ID}")

    for label, source, status_field in (
        ("torque", torque_result, "upstream_torque_review_status"),
        ("statics", statics_result, "upstream_statics_review_status"),
    ):
        try:
            review = review_engineering_result(source)
            setattr(result, status_field, review.status)
            if review.status != "PASS":
                result.errors.extend(f"{label} Reviewer: {error}" for error in review.errors)
        except (TypeError, ValueError, KeyError, OverflowError, ZeroDivisionError) as exc:
            setattr(result, status_field, "FAIL")
            result.errors.append(f"{label} Reviewer could not validate input: {exc}")

    if result.errors:
        return result

    # The Reviewer checked these fields. Preserve their Python values exactly.
    result.torque_nm = torque_result["torque_nm"]
    result.bending_moment_nm = statics_result["max_bending_moment_nm"]
    try:
        if isinstance(allowable_shear_mpa, bool) or not math.isfinite(allowable_shear_mpa):
            raise ValueError("allowable_shear_mpa must be finite")
        combined = calculate_solid_shaft_min_diameter_combined(
            result.bending_moment_nm, result.torque_nm, allowable_shear_mpa
        )
    except (TypeError, ValueError, OverflowError) as exc:
        result.errors.append(f"combined calculator failed: {exc}")
        return result

    result.combined_result = asdict(combined)
    try:
        review = review_engineering_result(result.combined_result)
        result.combined_review_status = review.status
        if review.status != "PASS":
            result.errors.extend(f"combined Reviewer: {error}" for error in review.errors)
    except (TypeError, ValueError, KeyError, OverflowError, ZeroDivisionError) as exc:
        result.combined_review_status = "FAIL"
        result.errors.append(f"combined Reviewer could not validate result: {exc}")
    if not result.errors:
        result.status = "PASS"
    return result


def _read_stdin() -> tuple[dict, dict]:
    lines = [line.strip() for line in sys.stdin if line.strip()]
    if len(lines) != 2:
        raise ValueError("stdin must contain exactly two non-empty JSON object lines: torque, then statics")
    objects = []
    for label, line in zip(("torque", "statics"), lines):
        try:
            value = json.loads(line, parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON constant: {value}")
            ))
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"invalid {label} JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{label} input must be a JSON object")
        objects.append(value)
    return objects[0], objects[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify and chain torque and multi-load statics JSON.")
    parser.add_argument("--allowable-shear-mpa", type=float, required=True)
    args = parser.parse_args()
    if not math.isfinite(args.allowable_shear_mpa):
        result = VerifiedShaftStrengthResult()
        result.errors.append("allowable_shear_mpa must be finite")
        print(json.dumps(asdict(result), allow_nan=False))
        return 2
    try:
        torque, statics = _read_stdin()
    except ValueError as exc:
        result = VerifiedShaftStrengthResult(allowable_shear_mpa=args.allowable_shear_mpa)
        result.errors.append(str(exc))
        print(json.dumps(asdict(result), allow_nan=False))
        return 2
    result = run_verified_shaft_strength_chain(torque, statics, args.allowable_shear_mpa)
    print(json.dumps(asdict(result), allow_nan=False))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
