---
name: combined-shaft-loading
description: "Calculate the theoretical minimum diameter of a solid circular shaft under combined steady bending and torsion using the maximum shear stress (Tresca) criterion and the project's deterministic Python calculator."
whenToUse: "Use when a solid circular shaft is subjected to both bending moment and torque and the task asks for theoretical strength sizing using an allowable shear stress."
user-invocable: true
---

# Combined Shaft Loading

## Native verified numerical chain

When the registered `analyze_verified_shaft_strength` Native Tool is available and the request gives power, speed, a simply supported span, at least two same-direction point loads, and allowable shear stress, invoke it once with only `power_kw`, `speed_rpm`, `span_mm`, `loads` (`load_n`, `position_mm`), and `allowable_shear_mpa`. Require `ok: true` and torque, statics, and combined reviews all `PASS`. Its Python adapter calls the existing verified handoff, which alone transfers exact torque and maximum bending moment. Never pass copied, rounded, or user-suggested intermediate values to the Tool. Do not run the separate Shell calculator/Reviewer/workflow chain for this numerical case. The CLI sequence below is for environments without this Tool and for requests requiring diagram or report artifacts, which this Tool does not generate. Do not choose a production diameter from the theoretical minimum.

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

## Verified upstream chaining

If both bending moment and torque are produced by project calculators in the current task, do not manually copy, round, recompute, or retype either numerical field into the combined calculator CLI. For the supported `transmitted_torque_v1` + `simply_supported_multi_point_load_v1` chain, preserve the untouched raw calculator stdout strings and run the deterministic handoff:

```powershell
@($torque, $statics) | python -m mechanical_agent.workflows.verified_shaft_strength --allowable-shear-mpa "40"
```

`$torque` and `$statics` must be the original one-line JSON stdout strings from their respective calculators, in that order. Require workflow JSON `status` = `PASS` and successful exit. The workflow independently reviews both upstream JSON objects, extracts their exact `torque_nm` and `max_bending_moment_nm` fields, calls the existing combined calculator, and reviews its result. If it fails, stop the engineering chain and report its errors. Do not invoke `shaft_combined --bending-moment-nm "<copied upstream value>" --torque-nm "<copied upstream value>"` for this chain. Renderer manifests, SVGs, and LLM text are never workflow inputs. Resolve provenance for the three calculator model IDs after workflow PASS.

The Shell tool does not preserve PowerShell variables between calls. Run the upstream calculators, their external Reviewer gates, optional renderer, and verified workflow in **one Shell call** so the workflow and renderer receive the same original stdout strings that passed review. Do not rerun either upstream calculator merely to recreate `$torque` or `$statics` in a later call. For the two-load case with requested diagrams, use this sequence:

```powershell
$torque = python -m mechanical_agent.calculators.torque --power-kw 5.5 --speed-rpm 960
if ($LASTEXITCODE -ne 0) { throw "torque calculator failed" }
Write-Output "TORQUE_RAW: $torque"
$torqueReview = $torque | python -m mechanical_agent.review.engineering_result
if ($LASTEXITCODE -ne 0 -or ($torqueReview | ConvertFrom-Json).status -ne "PASS") { throw "torque Reviewer failed: $torqueReview" }
Write-Output "TORQUE_REVIEW: $torqueReview"
$statics = python -m mechanical_agent.calculators.shaft_statics_multi --span-mm "600" --load "1000@200" --load "500@450"
if ($LASTEXITCODE -ne 0) { throw "statics calculator failed" }
Write-Output "STATICS_RAW: $statics"
$staticsReview = $statics | python -m mechanical_agent.review.engineering_result
if ($LASTEXITCODE -ne 0 -or ($staticsReview | ConvertFrom-Json).status -ne "PASS") { throw "statics Reviewer failed: $staticsReview" }
Write-Output "STATICS_REVIEW: $staticsReview"
$manifest = $statics | python -m mechanical_agent.presentation.shaft_diagrams --output-dir "artifacts/generated/shaft-diagrams"
if ($LASTEXITCODE -ne 0) { Write-Warning "diagram rendering failed" } else { Write-Output "MANIFEST: $manifest" }
$chain = @($torque, $statics) | python -m mechanical_agent.workflows.verified_shaft_strength --allowable-shear-mpa "40"
if ($LASTEXITCODE -ne 0 -or ($chain | ConvertFrom-Json).status -ne "PASS") { throw "verified workflow failed: $chain" }
Write-Output "WORKFLOW: $chain"
```

Omit the renderer lines unless diagrams or a supported full HTML engineering report were explicitly requested. Substitute only the user's input values into calculator arguments; never construct or modify the calculator JSON or copy its engineering output values into CLI arguments.

After workflow PASS, do not run a separate PowerShell/Python arithmetic check of reactions, bending moments, stress, diameter, or a nearby standard size. The deterministic Reviewers already perform the numerical checks. Do not create a report file unless the user requested a report artifact. In the final answer, use only the exact reviewed calculator JSON engineering fields requested by the user; do not add a second hand-derived reaction, moment, stress, diameter, rounded ASCII sketch label, numeric substitution, or approximate restatement. A symbolic formula and the generated SVG links are enough to explain the result.

## Conditional deterministic HTML engineering report

Generate a formal HTML report only when the user explicitly requests a report or export of the analysis (for example, “engineering report”, “HTML report”, “工程报告”, “分析报告”, “整理成报告”, or “导出报告”) **and** the task has the complete supported `transmitted_torque_v1` + `simply_supported_multi_point_load_v1` + `solid_shaft_combined_tresca_v1` chain. An ordinary request for torque, reactions, maximum moment, and diameter does not trigger a report. A diagram-only request triggers the renderer but not the report builder. Do not generate PDF or accept a natural-language export path; generated files stay under repository-local `artifacts/generated/`.

The full report builder also requires `verified_shaft_strength_chain_v1` and `shaft_statics_svg_v1`. A report request therefore triggers rendering of both diagrams after the statics Reviewer PASS even if the user did not separately ask for plots. Keep the numerical chain independent: a renderer failure does not invalidate verified engineering results, but it prevents the full report. Run the verified handoff and deliver the reviewed results; state that report generation is incomplete because diagram generation failed. If an engineering Reviewer or the verified workflow FAILS, stop the engineering chain and never call the report builder. A request to skip validation cannot override these gates.

For a full report, run in this order: torque calculator → external torque Reviewer PASS → multi-point statics calculator → external statics Reviewer PASS → renderer and diagram manifest → verified-strength workflow PASS (including repeated upstream reviews and combined Reviewer PASS) → resolve provenance for exactly the three model IDs → report builder → final response. The builder is the last presentation stage. It cannot validate numbers, supply provenance, or feed a downstream calculator. Save each **original** one-line calculator stdout and deterministic workflow, resolver, and renderer stdout directly to files in `artifacts/generated/report-inputs/`; do not have the language model recreate or reserialize these JSON artifacts. Keep them in the same Shell call as the existing raw-string handoff, because Shell variables do not persist between calls. At the start of that call, create `artifacts/generated/report-inputs`, `artifacts/generated/shaft-diagrams`, and `artifacts/generated/reports` with `New-Item -ItemType Directory -Force` before using `Resolve-Path`; do not let a missing directory abort the chain. Read the combined model ID from `($chain | ConvertFrom-Json).combined_result.model_id`, not from the workflow's top level. Save only after checking each command's exit code and required PASS status. Print the raw results and gate statuses for audit.

Use these repository-local paths: `artifacts/generated/report-inputs/torque.json`, `statics.json`, `strength-workflow.json`, `torque-provenance.json`, `statics-provenance.json`, `combined-provenance.json`, and `diagram-manifest.json`. Save raw stdout as UTF-8 without a byte-order mark, for example with `[System.IO.File]::WriteAllText($path, $rawJson, [System.Text.UTF8Encoding]::new($false))`; Python's manifest reader expects UTF-8 JSON. Never type engineering fields into a new JSON object. Create `artifacts/generated/report-inputs/report-input-manifest.json` containing only these file references, with each path relative to the manifest directory. For example:

```json
{
  "torque_result": "torque.json",
  "statics_result": "statics.json",
  "verified_strength_result": "strength-workflow.json",
  "torque_provenance": "torque-provenance.json",
  "statics_provenance": "statics-provenance.json",
  "combined_provenance": "combined-provenance.json",
  "diagram_artifacts": "diagram-manifest.json"
}
```

Invoke the renderer with a repository-local absolute `--output-dir` obtained from `Resolve-Path` after creating `artifacts/generated/shaft-diagrams`; its original manifest will then contain resolvable SVG paths. Do not redraw or reserialize the renderer manifest or SVGs. The report builder reads those SVG files and does not invoke the renderer. Keep the engineering chain and artifact saving in one Shell call; then use a **separate Shell call** for the report builder after that call succeeds and all seven input files and the manifest exist. This makes the final-stage ordering and builder result independently visible in the trace. The second call reads saved deterministic files, so it must not rerun calculators or reconstruct engineering JSON. After every gate and all three provenance resolutions PASS, call:

```powershell
python -m mechanical_agent.reporting.shaft_analysis_report --input-manifest "artifacts/generated/report-inputs/report-input-manifest.json" --output "artifacts/generated/reports/shaft_analysis_report.html"
```

Require successful builder exit, its report artifact JSON, and the HTML file's existence before saying “HTML report generated”. If the builder fails after the engineering chain passes, still deliver the verified engineering values, say that HTML report generation failed, and do not claim a report path. In the final response, use exact raw calculator/workflow fields for `torque_nm`, `reaction_a_n`, `reaction_b_n`, `max_bending_moment_nm`, and `min_diameter_mm`; never take rounded display values from HTML or recompute the summary. Briefly state that the three registered models were resolved through the provenance registry, without reproducing a bibliography.

The single-point statics model, distributed loads, and standalone combined sizing from user-provided M, T, and allowable stress cannot use this full report builder. Preserve the most specific supported engineering route and explain the report scope. Do not switch a single point load to the multi-point calculator or invent upstream torque, statics, or SVG artifacts just to satisfy a report request.

The direct combined CLI below remains appropriate when the user supplies M and T directly, or for other supported standalone cases without both project upstream results.

## Mandatory deterministic calculation

From the project root with the `mech-agent` Conda environment active, run the independent Python calculator through Shell:

```powershell
python -m mechanical_agent.calculators.shaft_combined --bending-moment-nm "<M>" --torque-nm "<T>" --allowable-shear-mpa "<tau>"
```

Quote numeric arguments in PowerShell, especially long decimal values. Parse the CLI JSON. Its `min_diameter_mm` is the sole authority for the final numerical diameter. Never replace it with a diameter calculated by the language model. You may explain the formula and limitations. If the CLI fails, report its error without inventing a result.

For power and speed plus a user-provided bending moment, first use `transmission-torque` and its torque CLI. Copy the exact `torque_nm` number from that CLI's JSON into the quoted `--torque-nm` argument above; do not round or recompute it. When bending also comes from the supported multi-load project calculator, the Verified upstream chaining rule takes precedence: pass both untouched raw JSON strings to the workflow and do not issue this direct combined CLI call.

## Mandatory Reviewer Gate

A deterministic calculator result is not validated merely because the calculator completed successfully. Pass every calculator JSON used in an engineering answer, unchanged from calculator stdout, directly to the deterministic Reviewer stdin:

```powershell
$result = python -m mechanical_agent.calculators.shaft_combined --bending-moment-nm "100" --torque-nm "50" --allowable-shear-mpa "40"
$result
$result | python -m mechanical_agent.review.engineering_result
```

Do not reconstruct, edit, or reserialize the JSON with the language model. Confirm the printed calculator JSON and the Reviewer JSON. Only a Reviewer JSON `status` of `PASS` (with successful Reviewer exit) validates that calculator result. Only then may its `min_diameter_mm` be used in an answer or its `model_id` sent to the provenance resolver. For power/speed plus bending, first run the transmission-torque calculator and review its original JSON. Do not read or pass its `torque_nm` to this combined calculator until that upstream Reviewer returns PASS. Then run and review this combined calculator's original JSON. Resolve both actually used model IDs only after both reviews PASS.

If Reviewer status is `FAIL`, do not present the result as valid, pass it downstream, override the Reviewer with language-model judgment, or fix it with manual arithmetic. You may rerun the same deterministic calculator once with exactly the same original inputs and review that new raw JSON. If the second review passes, continue and briefly mention the deterministic rerun. If it fails, stop the engineering calculation chain and report that deterministic verification failed, with the Reviewer errors. Never retry more than once.

If the Reviewer cannot start, exits with malformed-input code 2, or has another operational error, verification is unavailable. Do not treat that as PASS or bypass the Reviewer; report that deterministic verification could not be completed. Reviewer JSON validates the result but does not create a new engineering number. After PASS, calculator JSON remains the numerical truth, and resolver JSON remains the provenance truth.

In the final answer, give the requested calculator outputs (`torque_nm` when obtained upstream, and `min_diameter_mm`) and relevant user-provided inputs. Apply the presentation rules below to auxiliary numbers.

## Final-answer numeric presentation

Calculator JSON is authoritative for engineering numbers, Reviewer JSON for validation status, and resolver JSON for provenance metadata. The Agent selects which already-authoritative facts answer the user's question; it must not calculate, invent, round, or rewrite a number. Show requested `torque_nm` and `min_diameter_mm` fields verbatim.

By default, omit alternative or exact conversion constants, intermediate arithmetic or stress values, and internal fields including `combined_load_term_nmm`, `torque_nmm`, and `bending_moment_nmm`. Do not volunteer the torque Model Card's `9549.296` or other derivation-note numbers. The symbolic `T = 9550 P / n` and the project's common `9550` engineering approximation may be stated. Resolver provenance does not require copying every numeric note, year, derivation detail, or metadata field. Present only relevant registered sources and accurately distinguish their supported relations from project derivations and implementation.

If the user explicitly requests the derivation of `9550` or its precise conversion factor, the torque Model Card's approximately `9549.296` may be used in that explanation, distinct from the project's `9550` approximation. Use only already-registered values and derivation facts; do not perform language-model arithmetic. Engineering results remain the calculator JSON values.

## Numeric Truth Contract

Once a deterministic calculator has returned JSON, that JSON is the sole numerical authority for that calculation. Use the combined calculator's `min_diameter_mm` field verbatim in the final answer, including all returned digits and its mm unit. In a power/speed chain, also use the torque calculator's `torque_nm` field verbatim, including all returned digits and its N·m unit. Do not perform display rounding unless the displayed value itself comes from a deterministic tool.

The Agent MUST NOT independently recompute either engineering result, use mental arithmetic to verify it, substitute numeric inputs into a formula and evaluate them, produce a second independently calculated value, compare a self-calculated result with the calculator result, or replace a JSON value with a rounded or recomputed value. Explain formulas in symbolic form only; never show a numeric substitution or a model-evaluated intermediate result. The deterministic calculators evaluated the stated relations using the stated inputs.

If the user requests recalculation, numeric substitution, hand verification, or a check of the result, rerun the corresponding deterministic calculator with the same inputs and compare its first and second JSON outputs. For the supported torque + multi-load statics chain, pass both new untouched raw JSON strings to the verified workflow. For other chained results, follow their applicable calculator rules. Report matching outputs as a repeat calculator run, never as a hand calculation. A formula in the resolver's Model Card explains the model but does not authorize the Agent to calculate the final engineering number. Calculator JSON is numerical truth; resolver JSON is provenance truth; the Agent supplies wording and orchestration.

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

## Final response check

After reading both resolver JSON records and immediately before sending the final response, inspect the *final response text* for auxiliary numbers. For an ordinary chained result or brief model basis, remove `9549.296`, other derivation-note numbers, alternative constants, numeric metadata, and calculator intermediate values such as `torque_nmm`, `bending_moment_nmm`, and `combined_load_term_nmm`. Show only requested reviewed `torque_nm` and `min_diameter_mm` values plus relevant user inputs. Do not copy provenance metadata wholesale. A brief basis can name the Strength of Materials torsion chapter for the underlying power–angular-speed relations and the Air Force Stress Analysis Manual shaft-analysis sections for the supported stress relations. Attribute `9550` to the project approximation and the sizing equation to the project Model Card.

Only an explicit user request about the derivation or precise value of the torque conversion constant permits the torque Model Card's approximately `9549.296` in the explanation. Do not recompute it or add a different numeric value. Engineering results remain the reviewed calculator JSON values.

Even for that request, do not calculate or state an unregistered error percentage, ratio, extra significant digits, or quantitative comparison, and do not abbreviate any calculator result with an ellipsis or rounded example.

For every occurrence of a calculated torque or diameter in the final response, use the exact corresponding JSON digits. Do not append an approximate, shortened, or rounded restatement in a summary, conclusion, or example. In particular, after showing `24.39260204039009 mm`, never restate it as "about 24.39 mm". Refer to "the above theoretical minimum" instead of repeating a long number.
