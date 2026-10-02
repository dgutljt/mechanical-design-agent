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

## Mandatory Reviewer Gate

A deterministic calculator result is not validated merely because the calculator completed successfully. Pass every calculator JSON used in an engineering answer, unchanged from calculator stdout, directly to the deterministic Reviewer stdin:

```powershell
$result = python -m mechanical_agent.calculators.torque --power-kw 5.5 --speed-rpm 960
$result
$result | python -m mechanical_agent.review.engineering_result
```

Do not reconstruct, edit, or reserialize the JSON with the language model. Confirm the printed calculator JSON and the Reviewer JSON. Only a Reviewer JSON `status` of `PASS` (with successful Reviewer exit) validates that calculator result. Only then may its `torque_nm` be used in an answer, passed to a downstream shaft calculator, or its `model_id` sent to the provenance resolver. In a chain, review every calculator's original JSON and require PASS before consuming its result downstream; resolve all actually used model IDs only after all required reviews PASS.

If Reviewer status is `FAIL`, do not present the result as valid, pass it downstream, override the Reviewer with language-model judgment, or fix it with manual arithmetic. You may rerun the same deterministic calculator once with exactly the same original inputs and review that new raw JSON. If the second review passes, continue and briefly mention the deterministic rerun. If it fails, stop the engineering calculation chain and report that deterministic verification failed, with the Reviewer errors. Never retry more than once.

If the Reviewer cannot start, exits with malformed-input code 2, or has another operational error, verification is unavailable. Do not treat that as PASS or bypass the Reviewer; report that deterministic verification could not be completed. Reviewer JSON validates the result but does not create a new engineering number. After PASS, calculator JSON remains the numerical truth, and resolver JSON remains the provenance truth.

In the final answer, give the requested calculator output `torque_nm` and the user's inputs as numerical case values. Apply the presentation rules below to auxiliary numbers.

## Final-answer numeric presentation

Calculator JSON is authoritative for engineering numbers, Reviewer JSON for validation status, and resolver JSON for provenance metadata. The Agent selects which already-authoritative facts answer the user's question; it must not calculate, invent, round, or rewrite a number. When this calculator participates, show its `torque_nm` verbatim and any relevant user-provided inputs. The symbolic formula `T = 9550 P / n` and the wording "the project uses the common 9550 engineering approximation" are allowed.

By default, omit alternative or exact conversion constants, intermediate arithmetic or stress values, internal conversion fields such as `torque_nmm`, and Model Card derivation-note numbers. In particular, do not volunteer `9549.296`. Resolver provenance does not require copying every numeric note, year, derivation detail, or metadata field into the final answer. Cite only relevant registered sources and accurately distinguish what the source supports from the project's implementation.

If the user explicitly asks where `9550` comes from, why it is approximate, or for the precise conversion factor, explain the registered derivation using the Model Card and resolver. In that requested explanation, the Model Card's approximately `9549.296` may be shown as the mathematical unit-conversion value, distinct from the project's `9550` engineering approximation. Attribute the underlying `P = T * omega` and angular-speed relation to the registered source, not the project's approximation. Do not derive a different number with language-model arithmetic. The engineering result still comes only from calculator JSON.

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

## Final response check

After reading resolver JSON and immediately before sending the final response, inspect the *final response text* for auxiliary numbers. For an ordinary torque calculation or a request to briefly state the model basis, remove `9549.296` and all other derivation-note numbers, alternative constants, numeric metadata, and intermediate values. Do not copy the resolver's derivation note or source metadata wholesale. The final response may state `T = 9550 P / n`, call `9550` the project's common engineering approximation, and give the calculator's exact `torque_nm` plus relevant user inputs. A brief basis is enough: the Strength of Materials torsion chapter supports the underlying power–angular-speed relations; the project's Model Card specifies `9550`.

Only when the user explicitly asks to derive or compare the conversion constant may the final response include the Model Card's approximately `9549.296`, labeled as the mathematical unit-conversion value. Do not recompute it or add a different numeric value. This explicit-request exception applies only to the explanation; the engineering result remains the reviewed calculator JSON value.

For that explicit derivation request, stay within the registered derivation: `P = T * omega`, `omega = 2 * pi * n_rpm / 60`, and `60000/(2*pi) = approximately 9549.296`; distinguish this mathematical conversion from the project's `9550` approximation. Do not calculate or state a relative or absolute error, percentage, ratio, extra significant digits, or any quantitative comparison absent from the Model Card. Do not abbreviate the calculator result with an ellipsis or a rounded example anywhere in the final answer. Do not add claims about precision, uncertainty, common textbook usage, or design significance that the resolver does not establish.

For every occurrence of the transmitted torque in the final response, use the exact `torque_nm` JSON digits. Do not append an approximate, shortened, or rounded restatement in a summary, conclusion, or example. If repeating the full value would be awkward, refer to "the above torque result" without another number.
