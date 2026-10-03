---
name: shaft-point-load-statics
description: "Calculate support reactions and maximum bending moment for a simply supported shaft or beam with one transverse point load using the project's deterministic statics calculator."
whenToUse: "Use when a simply supported shaft or beam has one transverse point load between the supports and the task asks for reactions or maximum bending moment."
user-invocable: true
---

# Shaft Point Load Statics

Use only for two ideal simple supports, one transverse point load, one plane, and static loading. Reject multiple loads, distributed loads, overhung shafts, gear-force decomposition, two-plane loading, dynamic loading, and deflection. State clearly that the current Skill supports only one point load; never combine two loads or silently discard one.
For a distributed-load request, state that only discrete point loads are supported and stop. Do not offer an unreviewed distributed-load equation or design value as a substitute.

## Calculator and Reviewer Gate

From the project root run:

```powershell
$result = python -m mechanical_agent.calculators.shaft_statics --load-n "<F>" --span-mm "<L>" --load-position-mm "<a>"
$result
$result | python -m mechanical_agent.review.engineering_result
```

Pass original calculator stdout directly to Reviewer stdin without editing or reserializing JSON. The calculator JSON is numerical truth. Require Reviewer JSON `status` = `PASS` and successful exit before using `reaction_a_n`, `reaction_b_n`, `max_bending_moment_nm`, `max_moment_position_mm`, or passing the moment downstream. If Reviewer FAIL, stop the chain; at most rerun the same calculator once with the same inputs and review that new raw JSON. Never override a failure by manual arithmetic.

Never independently calculate reactions, maximum moment, or numerical equilibrium in the language model. Explain formulas only symbolically. For a requested check, use Reviewer or rerun the calculator. Copy requested result digits from reviewed calculator JSON without rounding. Omit internal N*mm values in an ordinary answer.

This prohibition also applies to intermediate reasoning: do not substitute the case inputs into an equation, mentally check a reaction or moment, or write arithmetic using case numbers after the calculator returns. Read the reviewed JSON fields and move directly to provenance and presentation. Do not add a second numerical explanation of why a displayed result is plausible.

Resolve provenance for the used `model_id` via `python -m mechanical_agent.knowledge_registry --model-id "<model_id>"` before answering. Resolver JSON is the authority for model and source claims. The registered Engineering Statics source supports the underlying free-body diagram and equilibrium approach; the one-load formulas are this project's algebraic derivation.

For a load to strength chain: review torque calculator JSON and statics calculator JSON separately. Only after both PASS, copy exact `torque_nm` and `max_bending_moment_nm` values into `combined-shaft-loading`; review its raw JSON and resolve all three unique model IDs before final response. Do not run combined sizing if either upstream review fails. State that the result is a theoretical minimum and describe unsupported fatigue, stress concentrations, deflection, dynamic loading, and final shaft design without inventing extra engineering numbers.
