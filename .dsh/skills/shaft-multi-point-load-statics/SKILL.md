---
name: shaft-multi-point-load-statics
description: "Calculate support reactions, piecewise shear/bending-moment data, and maximum bending-moment regions for a simply supported shaft or beam with multiple same-direction transverse point loads using the project's deterministic calculator."
whenToUse: "Use when a simply supported shaft or beam has two or more same-direction transverse point loads between the supports and the task asks for reactions, shear, bending moment, or maximum bending moment."
user-invocable: true
---

# Shaft Multi Point Load Statics

Use the most specific validated model: for one point load select `shaft-point-load-statics`; for two or more select this Skill. Require the support span and every load magnitude and position. Keep coincident loads as separate `--load` arguments. Never merge different-position loads, omit a load, guess a position, or discretize a distributed load.

The model requires two ideal simple supports, one plane, static loading, and non-negative same-direction transverse point loads on or between supports. It does not handle signed/opposite-direction loads, distributed loads, applied couples, overhangs, two-plane loading, dynamics, deflection, bearing stiffness, or shaft self-weight. State the supported boundary when asked for an unsupported case.
For an unsupported load class such as a distributed load, stop before invoking any calculator. Do not provide an unvalidated symbolic formula for that class as an alternative answer.

## Calculator and Reviewer Gate

From the project root, supply one `--load "FORCE_N@POSITION_MM"` argument per load:

```powershell
$result = python -m mechanical_agent.calculators.shaft_statics_multi --span-mm "600" --load "1000@200" --load "500@450"
$result
$result | python -m mechanical_agent.review.engineering_result
```

Pass the original calculator stdout directly to Reviewer stdin. Require Reviewer JSON `status` = `PASS` and successful exit before using reactions, maximum moment, regions, or any value downstream. If review fails, stop; at most rerun the same calculator once with identical inputs and review the new raw JSON. Never override failure with manual arithmetic.

Calculator JSON is numerical truth, Reviewer PASS is the validation gate, and provenance resolver JSON is source truth. The agent only sequences and presents results. Never recompute, round, numerically interpolate, or substitute case values into equations. Use `segments` values only when the user requests shear or moment detail. For a maximum plateau, report the entire `max_moment_regions` interval, not one endpoint.

Before sending the final answer, copy the exact JSON digit strings for each requested `reaction_a_n`, `reaction_b_n`, and `max_bending_moment_nm`; preserve all returned digits. Do not provide an approximate or shorter restatement in a table, paragraph, or summary. Show the `max_moment_regions` coordinates from JSON. In an ordinary answer, omit `total_load_n`, internal N*mm values, and the complete segment list unless specifically requested. Never infer an extra numerical trend or location from the segments. State self-weight as unsupported; do not recommend approximating it with point loads.

After PASS, resolve the used `model_id` with `python -m mechanical_agent.knowledge_registry --model-id "<model_id>"`. The registered statics source supports force/moment equilibrium and internal shear/bending-moment methodology. Multiple-load algebra, event segmentation, and the JSON schema belong to this project.

For a torque and strength chain, separately run and review the torque calculator and this statics calculator. Only after both PASS, pass the exact reviewed `torque_nm` and `max_bending_moment_nm` JSON fields into `combined-shaft-loading`. Review the combined calculator raw JSON and resolve exactly the three used model IDs. Any upstream FAIL stops the chain. State that the diameter is a theoretical minimum and identify unsupported fatigue, stress concentrations, deflection, and dynamic effects without inventing engineering numbers.
