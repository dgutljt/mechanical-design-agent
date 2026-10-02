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

## Numeric Truth Contract

Once a deterministic calculator has returned JSON, that JSON is the sole numerical authority for that calculation. Use the combined calculator's `min_diameter_mm` field verbatim in the final answer, including all returned digits and its mm unit. In a power/speed chain, also use the torque calculator's `torque_nm` field verbatim, including all returned digits and its N·m unit. Do not perform display rounding unless the displayed value itself comes from a deterministic tool.

The Agent MUST NOT independently recompute either engineering result, use mental arithmetic to verify it, substitute numeric inputs into a formula and evaluate them, produce a second independently calculated value, compare a self-calculated result with the calculator result, or replace a JSON value with a rounded or recomputed value. Explain formulas in symbolic form only; never show a numeric substitution or a model-evaluated intermediate result. The deterministic calculators evaluated the stated relations using the stated inputs.

If the user requests recalculation, numeric substitution, hand verification, or a check of the result, rerun the corresponding deterministic calculator with the same inputs and compare its first and second JSON outputs. For a chained result, rerun each calculator whose result is being checked and pass the original `torque_nm` JSON value directly to the combined calculator. Report matching outputs as a repeat calculator run, never as a hand calculation. A formula in the resolver's Model Card explains the model but does not authorize the Agent to calculate the final engineering number. Calculator JSON is numerical truth; resolver JSON is provenance truth; the Agent supplies wording and orchestration.

For example, with 100 N·m bending moment, 50 N·m torque, and 40 MPa allowable shear stress:

```powershell
python -m mechanical_agent.calculators.shaft_combined --bending-moment-nm "100" --torque-nm "50" --allowable-shear-mpa "40"
```

## Provenance before the final answer

Read `model_id` from each calculator JSON actually used. Before the final engineering answer, resolve every unique ID through Shell:

```powershell
python -m mechanical_agent.knowledge_registry --model-id "<model_id>"
```

For a power/speed → torque → combined shaft chain, resolve both the torque model ID and the combined shaft model ID. Resolution may follow all numerical calculations. Use each resolver JSON's model title, assumptions, limitations, and registered source name or organization plus section. The calculator JSON values are authoritative for numbers; resolver JSON values are authoritative for model basis and sources. Distinguish the torque reference from the combined-stress reference in the final answer. State that the diameter is a theoretical minimum and name key unchecked factors. Do not guess standards, books, or section numbers, and do not read `knowledge/*.toml` yourself to join source IDs. If resolution fails, report the error without inventing provenance.

### Attribution rules

- Calculator JSON is numerical-result truth only, not citation evidence. The resolver's Model Card (`model`) defines this project's equation, implementation convention, assumptions, limitations, and derivation notes. A registered source (`sources`) supports only the specific relations stated in its `supports` and notes.
- Do not attribute a project-specific approximation, rearranged equation, implementation choice, assumption, or limitation to a registered source unless the resolver output explicitly says that source supports that exact claim. If unsure, say: "The registered source supports the underlying relation; the project Model Card defines the implementation used here." Do not guess.
- For `solid_shaft_combined_tresca_v1`, attribute only `sigma = M*r/I`, `tau = T*r/J`, and `sqrt(tau^2 + (sigma/2)^2)` directly to the registered Air Force source. The solid-circle substitutions `sigma_b = 32M/(pi*d^3)` and `tau_t = 16T/(pi*d^3)`, as well as the combined `d_min` equation, are algebraic derivations recorded in the project Model Card. Do not say the manual directly gives these project forms unless the resolver explicitly supports that exact claim.
- When chaining `transmitted_torque_v1`, the registered OER supports the underlying power–torque and angular-speed relations; `9550` is the project's engineering approximation. Do not attribute `9550` directly to the OER unless its resolver source explicitly supports that claim.
- Name unchecked engineering factors by category only. Do not add numerical design limits, ranges, standard sizes, correction factors, or thresholds absent from the calculator and resolver output. Do not imply the registered source endorses every item in an expanded unchecked-factors list; its Section 10.6 only supports the need for further design checks as stated by the resolver.
