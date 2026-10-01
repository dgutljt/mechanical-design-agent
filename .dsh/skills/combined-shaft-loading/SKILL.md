---
name: combined-shaft-loading
description: "Calculate the theoretical minimum diameter of a solid circular shaft under combined steady bending and torsion using the maximum shear stress (Tresca) criterion and the project's deterministic Python calculator."
whenToUse: "Use when a solid circular shaft is subjected to both bending moment and torque and the task asks for theoretical strength sizing using an allowable shear stress."
user-invocable: true
---

# Combined Shaft Loading

## Model selection

Select the strength model from the stated load condition:

| Stated load | Skill to use |
| --- | --- |
| Torque only, with no bending | `solid-shaft-torsion` |
| Bending moment and torque | `combined-shaft-loading` |
| Bending moment only, explicitly no torque | `combined-shaft-loading` with `--torque-nm "0"` |
| Power and speed plus bending moment | `transmission-torque`, then `combined-shaft-loading` |

The combined calculator is mathematically valid at zero bending, but a pure-torsion request belongs to the more specific `solid-shaft-torsion` Skill. For power and speed plus bending, do not use `solid-shaft-torsion` as an intermediate sizing step.

## Scope and inputs

This Skill applies only to a solid circular shaft under steady bending moment and steady torque, with elastic stress analysis, known allowable shear stress, and theoretical minimum diameter under the maximum shear stress (Tresca) criterion. Bending moment and torque must be in N·m; allowable shear stress must be in MPa. Convert only unambiguous units. Do not guess any load, unit, or material property.

If bending is stated but its moment is missing, ask for the bending moment value and unit. Power and speed may first be used to calculate torque, but a pure-torsion diameter must not be presented as the combined result. If allowable shear stress is missing, ask for its value in MPa. An explicitly absent torque in a pure-bending request is zero; an unstated torque in a combined-loading request is missing, not zero.

This model excludes fatigue, alternating loading, shock or dynamic loading, keyways, shoulders, stress concentrations, axial force, stiffness, deflection, critical speed, and final shaft design. It does not select a standard or production diameter, add a safety factor, or choose a material. If asked for a final production diameter, give only the supported theoretical minimum when inputs are complete and clearly state that final sizing is unsupported. Do not round up to 25 mm, 30 mm, or another standard size.

## Mandatory deterministic calculation

From the project root with the `mech-agent` Conda environment active, run the independent Python calculator through Shell:

```powershell
python -m mechanical_agent.calculators.shaft_combined --bending-moment-nm "<M>" --torque-nm "<T>" --allowable-shear-mpa "<tau>"
```

Quote numeric arguments in PowerShell, especially long decimal values. Parse the CLI JSON. Its `min_diameter_mm` is the sole authority for the final numerical diameter. Never replace it with a diameter calculated by the language model. You may explain the formula and limitations. If the CLI fails, report its error without inventing a result.

For power and speed plus bending, first use `transmission-torque` and its torque CLI. Copy the exact `torque_nm` number from that CLI's JSON into the quoted `--torque-nm` argument above; do not round or recompute it. The Python calculators do not call one another. The Agent performs this sequence.

For example, with 100 N·m bending moment, 50 N·m torque, and 40 MPa allowable shear stress:

```powershell
python -m mechanical_agent.calculators.shaft_combined --bending-moment-nm "100" --torque-nm "50" --allowable-shear-mpa "40"
```
