---
name: transmission-torque
description: "Calculate transmitted torque from mechanical power and rotational speed using the project's deterministic Python calculator."
whenToUse: "Use when a task asks for transmitted torque and provides power and rotational speed, or values that can be safely converted to kW and rpm."
user-invocable: true
---

# Transmission Torque

## Purpose

Calculate steady transmitted torque from mechanical power P and rotational speed n. The current engineering formula is T = 9550 × P / n, where P is in kW, n is in rpm (r/min), and T is in N·m. The Python calculator uses the project's engineering approximation 9550.

## Mandatory deterministic calculation

Never compute the final numerical torque in the language model. From the project root, call the existing Python CLI:

```powershell
python -m mechanical_agent.calculators.torque --power-kw <P> --speed-rpm <n>
```

For example:

```powershell
python -m mechanical_agent.calculators.torque --power-kw 5.5 --speed-rpm 960
```

Parse the CLI's JSON output. Its `torque_nm` field is the sole authority for the numerical result. You may explain the formula, but do not replace the Python result with a number calculated by the model. If the CLI fails, report its error and do not invent a result.

## Numeric Truth Contract

Once a deterministic calculator has returned JSON, that JSON is the sole numerical authority for that calculation. Use the `torque_nm` field verbatim in the final answer, including all returned digits and its N·m unit. Do not perform display rounding unless the displayed value itself comes from a deterministic tool.

The Agent MUST NOT independently recompute the engineering result, use mental arithmetic to verify it, substitute numeric inputs into a formula and evaluate them, produce a second independently calculated value, compare a self-calculated result with the calculator result, or replace the JSON value with a rounded or recomputed value. Explain formulas in symbolic form only; never show a numeric substitution or a model-evaluated intermediate result. The deterministic calculator evaluated the stated relation using the stated inputs.

If the user requests recalculation, numeric substitution, hand verification, or a check of the result, rerun the same deterministic calculator with the same inputs and compare the first and second calculator JSON outputs. Report matching outputs as a repeat calculator run, never as a hand calculation. A formula in the resolver's Model Card explains the model but does not authorize the Agent to calculate the final engineering number. Calculator JSON is numerical truth; resolver JSON is provenance truth; the Agent supplies wording and orchestration.

## Units and missing information

The CLI accepts `power_kw` in kW and `speed_rpm` in rpm. Convert only unambiguous units before calling it: 5500 W is 5.5 kW; 16 r/s is 960 rpm. State any conversion used. Never guess units. If power or speed units are missing and context does not establish them, ask for clarification before calculating. Inputs explicitly stated in kW and r/min can be used directly.

## Scope

Use this skill for steady transmitted torque, the power-speed torque relation, and requests for transmitted torque with known kW and rpm. The current calculator does not cover starting or transient torque, acceleration inertia torque, motor stall torque, impact loading, cyclic torque, complex dynamics, shaft strength or diameter, or bearing selection. For those tasks, explain that this calculator does not support the requested analysis.

## Provenance before the final answer

Read `model_id` from the calculator JSON. Before the final engineering answer, resolve that ID through Shell:

```powershell
python -m mechanical_agent.knowledge_registry --model-id "<model_id>"
```

Use the resolver JSON's model title, assumptions, limitations, and registered source name or organization plus section to explain the result concisely. The calculator JSON is authoritative for the number; the resolver JSON is authoritative for model basis and sources. Do not guess citations or standards, and do not read `knowledge/*.toml` yourself to join sources. If provenance resolution fails, report the error and do not invent a source.

### Attribution rules

- Calculator JSON is numerical-result truth only, not citation evidence. The resolver's Model Card (`model`) defines this project's equation, implementation convention, assumptions, limitations, and derivation notes. A registered source (`sources`) supports only the specific relations stated in its `supports` and notes.
- Do not attribute a project-specific approximation, rearranged equation, implementation choice, assumption, or limitation to a registered source unless the resolver output explicitly says that source supports that exact claim. If unsure, say: "The registered source supports the underlying relation; the project Model Card defines the implementation used here." Do not guess.
- For `transmitted_torque_v1`, the registered Strength of Materials source supports `P = T * omega` and the angular-speed conversion. These yield a mathematical conversion factor of approximately `9549.296`; the project calculator uses `9550` as the engineering approximation recorded in the Model Card. Do not say the OER directly gives `9550` unless the resolver explicitly supports that claim.
- Do not replace the project attribution with an unsupported generalization such as "manuals commonly use 9550" or cite unnamed manuals. Keep the explanation to the requested kW/rpm units; do not add alternative unit coefficients unless the task asks for them and they have been checked.

When this Skill is chained with another calculator, resolve every unique `model_id` actually used before the final answer. Resolution may follow all numerical calculations. Keep the torque and shaft results, model bases, sources, and limitations distinguishable.

## Runtime

Start DeepSeek Harness from the repository root after `conda activate mech-agent`, using `npx.cmd @deepseek-ai/dsh web`. Its Shell should inherit the activated Python environment. Do not hard-code a machine-specific Python path.
