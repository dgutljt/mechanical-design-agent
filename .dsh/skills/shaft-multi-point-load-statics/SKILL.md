---
name: shaft-multi-point-load-statics
description: "Calculate support reactions, piecewise shear/bending-moment data, and maximum bending-moment regions for a simply supported shaft or beam with multiple same-direction transverse point loads using the project's deterministic calculator."
whenToUse: "Use for two or more same-direction transverse point loads between simple supports, or to enforce the unsupported boundary when a shaft report request has distributed or uniform loading. A report request never authorizes building a new load model."
user-invocable: true
---

# Shaft Multi Point Load Statics

For a complete supported numerical shaft-strength request with power, speed, span, two or more same-direction point loads, and allowable shear stress, use the registered `analyze_verified_shaft_strength` Native Tool when available. Supply only raw user inputs: `power_kw`, `speed_rpm`, `span_mm`, `loads` with `load_n` and `position_mm`, and `allowable_shear_mpa`. Its existing verified handoff enforces the three Reviewer gates and exact intermediate-value lineage. Do not run separate calculator or workflow CLI commands for this numerical request when the Native Tool is available. The CLI and rendering directions below still apply to standalone statics, diagram/report artifact requests, or environments without the Native Tool.

Use the most specific validated model: for one point load select `shaft-point-load-statics`; for two or more select this Skill. Require the support span and every load magnitude and position. Keep coincident loads as separate `--load` arguments. Never merge different-position loads, omit a load, guess a position, or discretize a distributed load.

The model requires two ideal simple supports, one plane, static loading, and non-negative same-direction transverse point loads on or between supports. It does not handle signed/opposite-direction loads, distributed loads, applied couples, overhangs, two-plane loading, dynamics, deflection, bearing stiffness, or shaft self-weight. State the supported boundary when asked for an unsupported case.
For an unsupported load class such as a distributed or uniform load, stop before invoking any calculator. Do not use the report request to implement a new calculator, model card, Reviewer contract, renderer, or report path within the DSH session. Explain the current model boundary and request a supported point-load case if the user wants this workflow. Do not provide an unvalidated symbolic formula for that class as an alternative answer.

## Calculator and Reviewer Gate

From the project root, supply one `--load "FORCE_N@POSITION_MM"` argument per load:

```powershell
$result = python -m mechanical_agent.calculators.shaft_statics_multi --span-mm "600" --load "1000@200" --load "500@450"
$result
$result | python -m mechanical_agent.review.engineering_result
```

Pass the original calculator stdout directly to Reviewer stdin. Require Reviewer JSON `status` = `PASS` and successful exit before using reactions, maximum moment, regions, or any value downstream. If review fails, stop; at most rerun the same calculator once with identical inputs and review the new raw JSON. Never override failure with manual arithmetic.

## Conditional Diagram Rendering

Render diagrams when the user explicitly requests a shear-force diagram, bending-moment diagram, SFD, BMD, 剪力图, 弯矩图, an engineering plot, or an equivalent visualization such as “把结果画出来”. A request for a full engineering or HTML report for the complete supported multi-point shaft strength chain also requires both diagrams, even without a separate drawing request, because the current report schema requires deterministic SVG artifacts. Do not render for ordinary numerical questions. Do not generate SVGs for ordinary numerical statics questions. The deterministic SVG renderer supports only `simply_supported_multi_point_load_v1`. A single point load still selects `shaft-point-load-statics`; do not switch models merely to obtain a diagram, hand-draw one, or construct SVG in the language model. Explain that deterministic SVG rendering for the single-point model is not integrated. Distributed loads remain unsupported and must not be discretized to obtain a diagram.

When diagrams are requested, the order is calculator → original calculator JSON → deterministic Reviewer PASS → SVG renderer → presentation manifest → provenance → final answer. Capture one calculator stdout value and pipe that exact raw JSON to both Reviewer and renderer. Do not hand-rebuild, edit, or reserialize its loads, segments, or other fields. Do not call the renderer before a Reviewer PASS, even if the user asks to skip validation. Require a successful Reviewer exit as well as `status == PASS`:

```powershell
$statics = python -m mechanical_agent.calculators.shaft_statics_multi --span-mm "600" --load "1000@200" --load "500@450"
if ($LASTEXITCODE -ne 0) { throw "multi-point statics calculator failed" }
$review = $statics | python -m mechanical_agent.review.engineering_result
if ($LASTEXITCODE -ne 0 -or ($review | ConvertFrom-Json).status -ne "PASS") { throw "statics review did not pass" }
$manifest = $statics | python -m mechanical_agent.presentation.shaft_diagrams --output-dir "artifacts/generated/shaft-diagrams"
if ($LASTEXITCODE -ne 0) { Write-Warning "SVG diagram generation failed; reviewed statics values remain valid" }
```

Run from the repository root and always use its `artifacts/generated/shaft-diagrams` directory for runtime diagrams. Do not take `--output-dir` from an ordinary natural-language request, including an absolute path or a path outside the repository. A future export feature needs a separate path policy. The renderer's stdout is a presentation manifest, not an engineering result. Its `renderer_id`, `input_model_id`, `shear_force_svg`, `bending_moment_svg`, `span_mm`, `shear_unit`, and `moment_unit` describe the generated artifacts; check the manifest and file existence before linking the diagrams. Never derive reactions, maximum moment, or other engineering numbers from the manifest or SVG geometry or labels. If rendering fails after calculator and Reviewer PASS, deliver the reviewed numerical results and clearly state that SVG generation failed or is unavailable; do not fabricate diagrams or relabel it an engineering verification failure.

Calculator JSON is numerical truth. Reviewer JSON is deterministic validation truth. Resolver JSON is provenance truth. Renderer manifest and SVG are presentation artifacts only. Do not read, measure, estimate, or infer engineering values from an SVG. SVG labels may format values for display; final numerical results must retain the exact calculator JSON digits.

After Reviewer PASS, do not perform a separate Shell arithmetic check of reactions, segment moments, maximum moment, stress, or diameter. The Reviewer already performs independent equilibrium and consistency checks. Do not include a numeric substitution, hand-derived intermediate, rounded ASCII diagram label, or shortened restatement of a JSON engineering value in the final answer. Refer to the generated SVGs and exact reviewed JSON fields.

Calculator JSON is numerical truth, Reviewer PASS is the validation gate, and provenance resolver JSON is source truth. The agent only sequences and presents results. Never recompute, round, numerically interpolate, or substitute case values into equations. Use `segments` values only when the user requests shear or moment detail. For a maximum plateau, report the entire `max_moment_regions` interval, not one endpoint.

Before sending the final answer, copy the exact JSON digit strings for each requested `reaction_a_n`, `reaction_b_n`, and `max_bending_moment_nm`; preserve all returned digits. Do not provide an approximate or shorter restatement in a table, paragraph, or summary. Show the `max_moment_regions` coordinates from JSON. In an ordinary answer, omit `total_load_n`, internal N*mm values, and the complete segment list unless specifically requested. Never infer an extra numerical trend or location from the segments. State self-weight as unsupported; do not recommend approximating it with point loads.

After PASS, resolve the used `model_id` with `python -m mechanical_agent.knowledge_registry --model-id "<model_id>"`. The registered statics source supports force/moment equilibrium and internal shear/bending-moment methodology. Multiple-load algebra, event segmentation, and the JSON schema belong to this project.

For a torque and strength chain, separately run and review the torque calculator and this statics calculator. Preserve each original raw calculator stdout string. After both external reviews PASS, pass the untouched torque JSON and untouched statics JSON, in that order, to `mechanical_agent.workflows.verified_shaft_strength` using its two-line stdin contract. Do not manually extract or retype `max_bending_moment_nm` or `torque_nm` into the combined calculator CLI. Require workflow PASS; it repeats both upstream reviews, transfers the exact fields, calls combined sizing, and reviews the combined result. When diagrams or a supported full report are requested, send the same original, already reviewed statics JSON to the renderer as an independent presentation branch. A report request does not broaden model selection: one point load still uses `shaft-point-load-statics`, and distributed loading stays unsupported. Neither case may use this multi-point calculator or the full report builder as a workaround. Never use its manifest or SVG as workflow input; renderer failure must not block the verified numerical strength chain. Resolve exactly the three used calculator model IDs after workflow PASS. Any upstream engineering Reviewer FAIL stops the chain and forbids diagrams from failed statics, combined sizing from failed upstream data, and delivery of the failed engineering result. State that the diameter is a theoretical minimum and identify unsupported fatigue, stress concentrations, deflection, and dynamic effects without inventing engineering numbers.
