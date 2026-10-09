# Verified overhung shaft screening workflow

`verified_overhung_two_plane_shaft_strength_chain_v1` is an independent Python-only
workflow. It does not register a DSH Native Tool or change the existing two-plane chain.

Run the fixed adapter from the repository with `PYTHONPATH=src`:

```text
python -m mechanical_agent.bridge.overhung_two_plane_workflow_adapter
```

It reads one JSON request from stdin (maximum 16,384 bytes), with no command arguments:

```json
{"contract_version":"1","operation":"verified_overhung_two_plane_shaft_strength_chain_v1","input":{"power_kw":5.5,"speed_rpm":960,"support_span_mm":600,"left_overhang_mm":100,"right_overhang_mm":100,"plane_1_loads":[{"load_n":-1000,"position_mm":-100}],"plane_2_loads":[{"load_n":500,"position_mm":700}],"allowable_shear_mpa":40,"assume_constant_torque_over_shaft":true}}
```

The workflow function takes exactly the same raw `input` object. Extra fields,
including intermediate torque, bending, diameter, Reviewer states, paths or commands,
are rejected before calculation. Numeric booleans and non-finite numbers are rejected.
Either or both load planes may be empty, as permitted by the existing statics model.
Support span must be positive, overhang lengths nonnegative with at least one positive,
loads within the shaft domain, and allowable shear positive.

`assume_constant_torque_over_shaft` must be the JSON boolean `true`. It explicitly
confirms that the user accepts constant transmitted torque over the entire shaft for
this screening calculation. It does **not** verify the actual axial torque distribution
or the positions where transmission elements apply torque. These problems, fatigue,
stress concentration, deflection and shoulders are outside this workflow. The output
is a theoretical elastic steady-load Tresca minimum diameter for a solid circular
shaft, not a completed real shaft design.

The chain calculates `transmitted_torque_v1` and
`two_support_overhung_two_plane_point_load_v1`, then invokes their existing independent
deterministic Reviewers separately. Both must return PASS before the existing
`solid_shaft_combined_tresca_v1` calculator is called. Its result requires a third
Reviewer PASS. Reviewers inspect copies and cannot overwrite the trusted source data.

All three gates use `review_bound_engineering_result()` from the public Reviewer
module. This new native entry point creates a private full snapshot, runs the same
existing numerical checks on it, and issues `BoundReviewResult`, which retains the
legacy review fields and adds `object_binding: ObjectBinding`. The binding records
version `engineering_object_binary64_v1`, purpose
`mechanical_agent.review.actual_engineering_object`, and a SHA-256 digest. The old
`review_engineering_result()` API, `ReviewResult` schema, CLI output, reviewer version
and numerical checks remain unchanged.

Encoding uses distinct type tags, eight-byte payload lengths, raw big-endian
binary64 bits, decimal integer bytes, and UTF-8 strings. String dictionary keys are
sorted; every key/value and nested field is included. Array order is preserved.
Integers, booleans and floats are distinct, including positive/negative zero and
adjacent floats. Unsupported Python types are rejected. Version and purpose are
inside the hashed payload. Review-time snapshot changes invalidate the evidence.
The workflow only compares the native evidence against its current result; it
never attaches a binding to received unbound PASS evidence. Any identity mismatch
returns `REVIEW_FAIL` without successful results or Lineage. The digest protects
against evidence/object mismatch, not malicious control of the trusted Reviewer
process. Existing numerical tolerances are unchanged.

Before calculation, the workflow retains an immutable tuple-based snapshot of
normalized binary64 power, speed, geometry and both load planes. Stable position
sorting preserves every duplicate station, force sign and signed zero. After the
upstream review gates, output geometry and every normalized load record must match
this snapshot bit-for-bit. Torque power/speed and constant must also match; its
reported value must exactly match the existing `9550.0 * float(power) / float(speed)`
binary64 evaluation order. This validation calculation is never used to fill or
replace a trusted intermediate value. A valid result for another request and a
one-ULP torque alteration both yield `REQUEST_BINDING_ERROR` before Combined runs.

All three review gates require the actual `BoundReviewResult` and `ReviewCheck` types,
expected model identity, `engineering_reviewer_v1`, typed error/warning lists,
nonempty checks with boolean `passed=true`, and the complete fixed check-name
multiset. The multiset includes every event station, segment, continuity/jump and
resultant check, with the correct zero-load/nonzero-load Combined branch. Missing,
unexpected or excess duplicate records fail. The unchanged Statics Reviewer emits
`plane_1_geometry` and `plane_2_geometry` twice each: once for valid reconstructed
geometry and once for its parent relation. Exactly those two occurrences are
required; this intentional naming overlap is not generalized to other checks.

The handoff copies the reviewed `torque_nm` and
`critical_resultant_bending_moment_nm` directly, with no conversion, resultant
reconstruction or decimal formatting. A bitwise binary64 comparison checks Combined's
echoed input fields, including signed zero. Lineage records source model IDs, fields,
units, exact machine values, coordinate convention, every critical station's position
and signed components, and every tied critical region. Plane 1 is M_z; plane 2 is -M_y,
as specified by the unchanged statics coordinate convention.

Before success, Registry provenance must resolve for all three model IDs and match
the fixed project module/function/source mappings and Tresca criterion. The returned
provenance includes model cards and source records, with their assumptions and
limitations. Any input, calculation, Reviewer, Lineage or Provenance failure yields
`ok=false` / `status=FAIL` and no engineering `results` or success Lineage. Review states
record PASS, FAIL or NOT_RUN; a failed upstream gate leaves Combined NOT_RUN.

The nested `two_support_overhung_signed_point_load_v1` model is also required in
the fixed Registry validation and returned provenance. Its model card must map to
`mechanical_agent.calculators.shaft_statics_overhung` /
`calculate_two_support_overhung_signed_point_loads` and the
`engineering_statics_beam_equilibrium` source. Lineage explicitly relates this model
to `statics.plane_1` (M_z) and `statics.plane_2` (-M_y) under the two-plane parent
model. Missing cards, parse errors, incorrect module/function mappings or source IDs
yield `PROVENANCE_ERROR`; callers cannot supply provenance or override mappings.

The 14B-1 exact rational arithmetic and binary64 rounding contract are unchanged.
Its approximately O(n²) computation and independent review still impose a performance
cost. Measuring this cost and demonstrating completion within the Native 20-second
timeout are mandatory acceptance gates before Phase 14C; this Python-only workflow
does not claim that Native gate is satisfied and performs no performance optimization.

Local cost sample (2026-10-09, existing Anaconda Python, one timed run per size,
not a performance guarantee): one populated plane, alternating signed loads at
distinct positions across [-100,700], L=600, a=b=100, second plane empty. Timings
include Calculator output conversion to dictionaries; Reviewer is timed separately.
This measures the underlying Python model directly, independently of adapter byte limits.

| Point loads | Calculator seconds | Independent Reviewer seconds |
| --- | ---: | ---: |
| 100 | 0.062745 | 0.063549 |
| 200 | 0.243062 | 0.211352 |
| 400 | 0.955293 | 0.790337 |
| 800 | 4.250935 | 3.510499 |

The observed scaling remains consistent with approximately quadratic cost. Full
Native process startup, two populated planes and larger inputs need separate timeout
acceptance testing before Phase 14C. No load-count cap or algorithm change was added.
