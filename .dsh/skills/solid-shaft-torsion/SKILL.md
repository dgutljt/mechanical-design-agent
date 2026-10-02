---
name: solid-shaft-torsion
description: "Calculate the theoretical minimum diameter of a solid circular shaft under pure steady torsion using the project's deterministic Python calculator."
whenToUse: "Use when a task asks for the theoretical minimum diameter or torsional sizing of a solid circular shaft and provides torque plus allowable shear stress."
user-invocable: true
---

# Solid Shaft Torsion

## Purpose and limits

Use this Skill only for a solid circular shaft under pure steady torsion with known transmitted torque and allowable shear stress. It computes the theoretical minimum diameter, not a final engineering shaft diameter. The relation is `d_min = (16 T / (pi * tau_allow))^(1/3)`, with torque converted from N·m to N·mm and allowable shear stress in MPa (N/mm²).

This model does not account for bending, fatigue, keyways, stress concentrations, shock factors, stiffness, standard preferred sizes, shoulders, or combined loading. Do not claim it determines a final shaft diameter. If a request requires any excluded effect or a final shaft design diameter, state that the current calculator cannot perform it and identify the excluded effects. Stop there: do not run this CLI, ask for more design inputs, offer a workflow or feature expansion, or provide formulas, coefficients, or numerical rules for the unsupported design. Do not add a safety factor, choose a material, or round up to a standard size.

## Mandatory deterministic calculation

Never calculate the final numerical diameter in the language model. From the project root, run:

```powershell
python -m mechanical_agent.calculators.shaft_torsion --torque-nm <T> --allowable-shear-mpa <tau>
```

For example:

```powershell
python -m mechanical_agent.calculators.shaft_torsion --torque-nm "54.713541666666664" --allowable-shear-mpa 30
```

On PowerShell, quote the numeric torque argument as a string so all digits reach Python; an unquoted long decimal can be rounded by PowerShell. When chaining, copy the exact `torque_nm` value from the first calculator's JSON into that quoted argument. Do not round, recompute, or reduce its significant digits. Parse the CLI JSON. Its `min_diameter_mm` field is the sole authority for the numerical diameter. You may explain the formula and assumptions, but do not replace the Python result with a model-calculated value. If the CLI fails, report the error without inventing a result.

## Mandatory Reviewer Gate

A deterministic calculator result is not validated merely because the calculator completed successfully. Pass every calculator JSON used in an engineering answer, unchanged from calculator stdout, directly to the deterministic Reviewer stdin:

```powershell
$result = python -m mechanical_agent.calculators.shaft_torsion --torque-nm "54.713541666666664" --allowable-shear-mpa 30
$result
$result | python -m mechanical_agent.review.engineering_result
```

Do not reconstruct, edit, or reserialize the JSON with the language model. Confirm the printed calculator JSON and the Reviewer JSON. Only a Reviewer JSON `status` of `PASS` (with successful Reviewer exit) validates that calculator result. Only then may its `min_diameter_mm` be used in an answer or its `model_id` sent to the provenance resolver. If torque comes from the transmission calculator, review that calculator's raw JSON first; do not read or pass its `torque_nm` to this calculator until its Reviewer PASS. Review this shaft calculator's raw JSON as well, and resolve both actually used model IDs only after both reviews PASS.

If Reviewer status is `FAIL`, do not present the result as valid, pass it downstream, override the Reviewer with language-model judgment, or fix it with manual arithmetic. You may rerun the same deterministic calculator once with exactly the same original inputs and review that new raw JSON. If the second review passes, continue and briefly mention the deterministic rerun. If it fails, stop the engineering calculation chain and report that deterministic verification failed, with the Reviewer errors. Never retry more than once.

If the Reviewer cannot start, exits with malformed-input code 2, or has another operational error, verification is unavailable. Do not treat that as PASS or bypass the Reviewer; report that deterministic verification could not be completed. Reviewer JSON validates the result but does not create a new engineering number. After PASS, calculator JSON remains the numerical truth, and resolver JSON remains the provenance truth.

In the final answer, give the requested calculator output `min_diameter_mm`, any upstream requested calculator output, and relevant user-provided inputs. Apply the presentation rules below to auxiliary numbers.

## Final-answer numeric presentation

Calculator JSON is authoritative for engineering numbers, Reviewer JSON for validation status, and resolver JSON for provenance metadata. The Agent selects which already-authoritative facts answer the user's question; it must not calculate, invent, round, or rewrite a number. Show requested result fields such as `min_diameter_mm` and, when calculated upstream, `torque_nm` verbatim.

By default, omit alternative or exact conversion constants, intermediate arithmetic or stress values, internal conversion fields such as `torque_nmm`, and Model Card derivation-note numbers. In a chain, do not volunteer the torque Model Card's `9549.296`; the symbolic `T = 9550 P / n` and the project's common `9550` engineering approximation may be stated. Resolver provenance does not require copying every numeric note, year, derivation detail, or metadata field. Present only relevant registered sources and their supported relations, without attributing a project-specific approximation to a source.

If the user explicitly requests the derivation of `9550` or its precise conversion factor, the torque Model Card's approximately `9549.296` may be used in that explanation, distinct from the project's `9550` approximation. Use only already-registered values and derivation facts; do not perform language-model arithmetic. Engineering results remain the calculator JSON values.

## Numeric Truth Contract

Once a deterministic calculator has returned JSON, that JSON is the sole numerical authority for that calculation. Use the `min_diameter_mm` field verbatim in the final answer, including all returned digits and its mm unit. If torque came from the transmission calculator, likewise use its `torque_nm` field verbatim. Do not perform display rounding unless the displayed value itself comes from a deterministic tool.

The Agent MUST NOT independently recompute either engineering result, use mental arithmetic to verify it, substitute numeric inputs into a formula and evaluate them, produce a second independently calculated value, compare a self-calculated result with the calculator result, or replace a JSON value with a rounded or recomputed value. Explain formulas in symbolic form only; never show a numeric substitution or a model-evaluated intermediate result. The deterministic calculator evaluated the stated relation using the stated inputs.

If the user requests recalculation, numeric substitution, hand verification, or a check of the result, rerun the corresponding deterministic calculator with the same inputs and compare its first and second JSON outputs. For a chained result, rerun each calculator whose result is being checked and pass the original `torque_nm` JSON value directly to the shaft calculator. Report matching outputs as a repeat calculator run, never as a hand calculation. A formula in the resolver's Model Card explains the model but does not authorize the Agent to calculate the final engineering number. Calculator JSON is numerical truth; resolver JSON is provenance truth; the Agent supplies wording and orchestration.

## Inputs and Skill chaining

If allowable shear stress is missing, ask exactly for the user-provided value in MPa: "请提供许用剪应力（MPa）的数值。" Do not append an example number, material grade, suggested range, or prefilled numeric answer option. Never infer a material property or insert an assumed value. If the user supplies power, rotational speed, and allowable shear stress but no torque, the Agent may first use the independent `transmission-torque` Skill to obtain `torque_nm` from its Python CLI JSON, then pass that exact returned value to this Skill's CLI. The two Python calculators remain independent; this sequence is Agent orchestration.

## Provenance before the final answer

Read `model_id` from the shaft calculator JSON. Before the final engineering answer, call through Shell:

```powershell
python -m mechanical_agent.knowledge_registry --model-id "<model_id>"
```

Use its JSON model title, assumptions, limitations, and registered source name or organization plus section. The calculator JSON supplies the numerical diameter; the resolver JSON supplies model basis and source facts. State that the result is a theoretical minimum, not a final production diameter. Do not guess sources or standards, and do not read `knowledge/*.toml` yourself to join source IDs. If resolution fails, report the error without inventing provenance.

### Attribution rules

- Calculator JSON is numerical-result truth only, not citation evidence. The resolver's Model Card (`model`) defines this project's equation, implementation convention, assumptions, limitations, and derivation notes. A registered source (`sources`) supports only the specific relations stated in its `supports` and notes.
- Do not attribute a project-specific approximation, rearranged equation, implementation choice, assumption, or limitation to a registered source unless the resolver output explicitly says that source supports that exact claim. If unsure, say: "The registered source supports the underlying relation; the project Model Card defines the implementation used here." Do not guess.
- For `solid_shaft_pure_torsion_v1`, attribute the torsional stress relation to the registered source. Describe the minimum-diameter equation as algebraically derived from that relation for the project model, as recorded in the Model Card; do not say the manual directly gives this exact project equation unless the resolver explicitly supports it.

If torque came from a separate calculator, resolve every unique `model_id` actually used before answering, including the torque model. Resolution may happen after all calculations. Clearly attribute each result to its own model and source.

Start DeepSeek Harness from the project root with the `mech-agent` Conda environment active so Shell can run the installed Python modules.

## Final response check

After reading all resolver JSON and immediately before sending the final response, inspect the *final response text* for auxiliary numbers. For an ordinary shaft result or brief model basis, remove `9549.296`, other derivation-note numbers, alternative constants, numeric metadata, and calculator intermediate values such as `torque_nmm`. Show only requested reviewed calculator result fields and relevant user inputs. Do not copy provenance metadata wholesale; cite the relevant registered source and distinguish its supported relation from the project's derivation.

Only an explicit user request about the derivation or precise value of the torque conversion constant permits the torque Model Card's approximately `9549.296` in the explanation. Do not recompute it or add a different numeric value. Engineering results remain the reviewed calculator JSON values.

Even for that request, do not calculate or state an unregistered error percentage, ratio, extra significant digits, or quantitative comparison, and do not abbreviate any calculator result with an ellipsis or rounded example.

For every occurrence of a calculated torque or diameter in the final response, use the exact corresponding JSON digits. Do not append an approximate, shortened, or rounded restatement in a summary, conclusion, or example. Refer to "the above result" instead of repeating a long number.
