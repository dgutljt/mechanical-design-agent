# V0.2 Mechanical Scope — Balanced

Status: 2026-10-03. This document formalizes the ChatGPT-reviewed **PASS** conclusion of Phase 13A into the plan of record for v0.2. It records already-approved scope only; it introduces no new mechanical content and authorizes no implementation by itself. Each phase in §13 still follows the established review-then-commit discipline.

## 1. Current baseline

- Repository `mechanical-design-agent`, branch `master`, HEAD `aab06737e2a168134756526167f707896abd578d` (`test: add reproducible V1.5 runtime acceptance`). `v0.1.0` = `eb8c59755f7dde7f529089dd4bb74d99e0b2bfc1`.
- Verified v1 chain: transmitted torque (steady, from power/speed); simply supported single-plane multi-point statics for same-direction transverse point loads (model `simply_supported_multi_point_load_v1`); solid-shaft torsion sizing; combined bending + torsion review producing a theoretical minimum diameter. Every chain stage is gated by separate Reviewers, intermediate values move only through Verified Handoff, and every model resolves through Knowledge Registry provenance.
- V1.5 Native DSH architecture (Phases 12A–12E) is functionally closed: DSH `0.2.0-rc.2`, plugin at `packages/dsh-mechanical-plugin`, two reviewed Native Tools (`calculate_transmitted_torque`, `analyze_verified_shaft_strength`), restricted Mechanical Engineering profile via `.dsh/mechanical-engineering.patch.yml` (pinned 10-tool inventory), reproducible acceptance via `scripts/verify_v15_runtime.mjs`, full suite at 232 tests, V1 golden demo unchanged.

## 2. Why v0.2 exists

The v1 statics model accepts only same-direction transverse point loads in one plane. Real shaft inputs are signed and typically arrive in two perpendicular planes (for example radial gear forces and belt pulls acting in different directions). v0.2 extends the verified, review-gated chain to signed point loads and two-plane bending without weakening any v1 guarantee: every released number still comes from Python calculators, passes Reviewer gates, transfers through Verified Handoff, and resolves registry provenance. "Balanced" means the smallest mechanical generalization that removes the largest real-usage blocker — and nothing beyond §3 (see §12).

## 3. Approved v0.2 scope

- Simply supported shafts with **signed transverse point loads only** (each load keeps a positive magnitude; its transverse direction is signed).
- A **signed single-plane point-load model** as the foundation (§5).
- A **two-plane bending model**: loads resolved into two perpendicular planes, per-plane bending from signed loads (§6).
- The **same-station resultant bending rule**: resultant evaluated at one common station; under the v0.2 restrictions its maximum is determined at common-event endpoints (§7).
- Critical-result **context retained as deterministic machine data** (Addendum B, §6.1).
- Reviewer, Verified Handoff, and Knowledge Registry extensions with unchanged gate discipline (§8–§10).
- Exposure through the existing Native Tool/plugin architecture as a new versioned operation; existing v1 Native Tools unchanged (§11).
- Everything not listed here is out of scope (§12).

## 4. Mechanical dependency chain

The chain shape is unchanged; v0.2 generalizes the statics stage:

```
transmitted torque
  → per-plane statics (signed point loads, two perpendicular planes)
  → same-station resultant bending moment (critical station + components)
  → combined bending + torsion review
  → theoretical minimum diameter
```

Lineage rules are unchanged: exact intermediate transfer between stages, no stage recomputes an upstream value, and the LLM never performs engineering arithmetic, validation, lineage, or provenance decisions.

## 5. Signed single-plane point-load foundation

The first v0.2 deliverable generalizes single-plane simply supported multi-point statics to **signed transverse point loads**: support reactions and the bending moment distribution are computed for loads whose transverse direction may be either sense, in one plane. This foundation is the prerequisite for two-plane resolution (§6); the two-plane model must not be built before it exists and is verified.

### 5.1 Review Addendum A — Preserve v1 model semantics

- The model semantics of `simply_supported_multi_point_load_v1` **must not be modified**.
- The signed point-load capability **must use a new versioned `MODEL_ID`** (assigned at implementation time; versioned; never reusing or overloading the v1 ID).
- The old model, its Reviewer, its Registry entries, and the V1 Demo **stay as they are**. v0.2 adds capability; it does not edit v1 behavior. This mirrors the Phase 12B/12C rule: adapters call verified code, and golden artifacts are untouched.

## 6. Two-plane bending model

Simply supported shaft; signed transverse point loads decomposed into two perpendicular planes (plane 1, plane 2). Per-plane support reactions and bending components `M1(x)`, `M2(x)` follow the signed single-plane foundation of §5. Torsion is unchanged from v1 (steady transmitted torque). The two-plane model is a separate, new, versioned `MODEL_ID` (same rule as Addendum A).

### 6.1 Review Addendum B — Two-plane critical result must retain context

Besides `critical_resultant_bending_moment_nm`, the two-plane model must also return:

- the **critical station / region**,
- the **bending component in plane 1 at that station**,
- the **bending component in plane 2 at that station**.

These are **deterministic machine data**, used for Reviewer verification, lineage, debugging, and future critical-section design. The LLM must not reconstruct, recompute, round, or summarize them into substitutes.

## 7. Same-station resultant bending rule

The resultant bending moment is defined at a single common station `x` as the magnitude of the two perpendicular plane components (square root of the sum of their squares). The critical resultant is the maximum of this magnitude over the span, evaluated at one station.

**Project mathematical derivation.** For the v0.2-restricted load space — **simply supported, signed transverse point loads only, no distributed loads, no applied couples** — both bending components `M1(x)` and `M2(x)` are linear functions within every interval bounded by consecutive common events (the union of load stations from both planes, including the supports). With both components linear on such an interval, each squared component is a convex quadratic in `x`; their sum is convex quadratic, and the magnitude is a monotone transform of that sum, so the magnitude attains its maximum on each closed interval at an interval endpoint. Therefore the maximum resultant bending moment over the span is determined by evaluating the resultant at the common-event endpoints only.

This argument is a **project mathematical derivation** for the v0.2-restricted load space. It must not be presented, cited, or registered as an algorithm given directly by an external reference (see §10).

Implementation rule: the two-plane model segments the span into common-event intervals, evaluates the resultant at every common-event endpoint, and selects the maximum. The selected station and both components at it are returned as Addendum B context.

## 8. Reviewer requirements

- Gate discipline is unchanged: separate torque, statics, and combined reviews; classified PASS/FAIL outcomes; a FAIL never releases a validated result.
- The extended statics review must verify: signed load handling and equilibrium in each plane; correct common-event segmentation; resultant evaluation at all common-event endpoints (no interior-point heuristics or sampling); consistency between the reported critical station, both plane components, and `critical_resultant_bending_moment_nm` (Addendum B); and the v0.2 input restrictions (reject distributed loads, applied couples, overhung supports, axial loads).
- Reviewers verify; they do not recompute the chain. Exact intermediates arrive through Verified Handoff (§9).

## 9. Verified Handoff requirements

- Exact intermediate transfer is preserved: torque → statics → resultant → combined. No copied, rounded, or model-suggested intermediate values, as in v1.
- The two-plane handoff must carry the Addendum B context — critical station, plane-1 component, plane-2 component — deterministically inside the validated payload, so lineage records which station produced the critical resultant.
- The v1 handoff path remains untouched (Addendum A).

## 10. Knowledge Registry / provenance requirements

- New models register under their own versioned `MODEL_ID`s with source attributions; v1 Registry entries remain unchanged.
- The same-station resultant endpoint rule (§7) must be registered with provenance marked as a **project mathematical derivation** (internal, valid for the v0.2-restricted load space), not as externally sourced.
- Provenance for two-plane results must resolve every consumed model before a result is released, as in v1.

## 11. Native Tool implications

- The v0.2 capability ships through the existing plugin architecture (`packages/dsh-mechanical-plugin`) as a **new versioned Native operation**, following the Phase 12B/12C pattern: raw-input-only argument schema (no torque or bending-moment override fields), a thin Python adapter that calls the verified chain, typed output schema, and failure envelopes for classified outcomes.
- When the new operation is mounted, the restricted profile's Tool inventory and policy artifacts (`scripts/v15-policy.json`, `.dsh/mechanical-engineering.patch.yml`) must be updated and re-fingerprinted, and the V1.5-style acceptance extended.
- The existing Native Tools `analyze_verified_shaft_strength` (v1 chain) and `calculate_transmitted_torque` keep their names and semantics unchanged.

## 12. Explicit v0.2 non-goals

v0.2 explicitly does **not** include:

- distributed loads
- applied couples
- overhung shafts
- axial loads
- variable torque
- shoulders/keyways/grooves
- Kt/Kts
- fatigue
- materials database
- automatic allowable stress
- production diameter selection
- deflection
- torsional angle
- critical speed
- bearings
- gear/pulley/sprocket load generators
- CATIA
- CAE
- PDF

Requests outside the approved scope are refused with an explanation, never answered with an unreviewed calculation — same policy as v1/V1.5.

## 13. Planned phases 13B–13F

Planning-level sequence of record. Each phase is implemented, reviewed, and committed separately; no phase pre-authorizes the next.

- **13B — Signed single-plane foundation.** New versioned signed point-load statics model (calculator + tests) per §5; v1 artifacts untouched (Addendum A).
- **13C — Two-plane bending model.** Per-plane signed statics, common-event segmentation, endpoint evaluation of the resultant with Addendum B context; new versioned `MODEL_ID` + tests (§6, §7).
- **13D — Verified chain integration.** Reviewer gates for signed/two-plane statics, Verified Handoff context transfer, Knowledge Registry entries including project-derivation provenance (§8–§10).
- **13E — Native Tool exposure.** Plugin contract/bridge/index/adapter updates and tests; restricted profile inventory/policy/fingerprint update (§11).
- **13F — Acceptance and docs.** Skills and README updates, V1.5-style runtime acceptance extension, full regression including the V1 demo, release scoping (§14).

## 14. Release acceptance concept

v0.2 may be released only when all of the following hold:

1. Every phase 13B–13F passed ChatGPT review and was committed under the established scope-verification discipline.
2. The full suite (pytest + plugin node tests) is green, including coverage of the new models and the untouched v1 tests.
3. The V1 golden demo (`examples/v1-shaft-analysis/expected/`) remains byte-stable.
4. The extended V1.5-style acceptance passes: pinned DSH version, effective composed-profile validation, bundle/config fingerprint, exact Tool inventory including the new operation, fresh torque/two-plane/adversarial sessions, and the unpatched developer-profile check.
5. README and Skills document exactly the shipped Tool inventory and the v0.2 capability boundary.

Tagging and any version bump happen only in a dedicated release step after the above, never as a side effect of a phase commit.
