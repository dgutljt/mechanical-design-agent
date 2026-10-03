# Reproducible V1 Shaft Analysis

## What this example demonstrates

This example runs deterministic torque and multi-point shaft statics calculations, Reviewer gates, Verified Handoff, three provenance resolvers, SVG shear-force and bending-moment diagrams, and a deterministic HTML report. It needs no LLM or DSH session.

## Input

The fixed case is 5.5 kW at 960 rpm, a 600 mm span, 1000 N at 200 mm, 500 N at 450 mm, and 40 MPa allowable shear stress. See [input.json](input.json).

## Expected results

| Result | Value |
| --- | ---: |
| Torque | 54.713541666666664 N·m |
| Reaction A | 791.6666666666667 N |
| Reaction B | 708.3333333333333 N |
| Maximum bending moment | 158.33333333333334 N·m |
| Theoretical minimum diameter | 27.732717671613003 mm |

The maximum moment is at 200 mm. The raw regression contract is [expected_results.json](expected_results.json).

## Run

From the repository root on Windows:

```powershell
conda activate mech-agent
python examples/v1-shaft-analysis/run_demo.py --output-dir artifacts/generated/v1-demo
```

Without `--output-dir`, the script writes to `examples/v1-shaft-analysis/generated/`.

## Verify

```powershell
python examples/v1-shaft-analysis/run_demo.py --verify
```

`--verify` runs the full pipeline, checks raw results and PASS statuses, and compares both SVGs and the HTML report byte for byte with `expected/`. It exits nonzero on a mismatch and never rewrites the golden files. DSH orchestration is optional for this deterministic reproduction example.
