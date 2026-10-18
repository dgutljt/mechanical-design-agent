# Verified overhung shaft screening workflow

Project target **v0.3.0** exposes the existing verified Python workflow as the explicit
DSH Native Tool `verified_overhung_two_plane_shaft_strength_chain_v1`. DSH, DSH Tools
and the Win32 process provider remain **0.2.0-rc.2**. The default product profile
still mounts eleven Tools and the three existing engineering operations; the
explicit profile adds only this twelfth Tool. The old two-plane workflow is unchanged.
This release-preparation candidate awaits independent review and Gatekeeper approval.

Older model-card notes about Native/Handoff exposure record their original phase's
scope. The explicit exposure described here adds no change to those models'
engineering assumptions or limitations.

## Native activation and transport

With compatible dependencies already available and the interpreter selected through
`MECHANICAL_AGENT_PYTHON` / `MECHANICAL_AGENT_TEST_PYTHON`, run from the repository:

```powershell
.\start-mechanical-overhung-dsh.cmd
```

The launcher builds, checks the explicit configuration, uses a fresh temporary
DSH_HOME and no listening port, then reads one task. Empty input/EOF cancels safely.
Nonempty model requests need provider/model configuration for that isolated home;
credentials are not copied from the default home. The launcher startup/EOF route
and actual DSH ToolRuntime execution were exercised separately. For an already
configured home, the equivalent explicit headless selection is:

```powershell
node packages/dsh-mechanical-plugin/scripts/build.mjs
node packages/dsh-mechanical-plugin/node_modules/@deepseek-ai/dsh/lib/bin.js --profile headless --patch .dsh/mechanical-overhung.patch.yml
```

The new plugin is imported only by `.dsh/mechanical-overhung.patch.yml`, with
`enableVerifiedOverhung: true`; incorrect/missing opt-in or failed loading stops
startup. Its closed outer input is `{request_json: string}` and closed outer output
is `{response_json: string}`. Both fields are required; extra fields are forbidden.
Each string contains the complete P1A numeric envelope. A carrier is not engineering
success: consumers must inspect the inner `ok`, errors, reviews, provenance and lineage.

The lexical gate rejects duplicate decoded keys (including Unicode aliases), tails
and malformed numbers before the existing preflight. Original input is bounded
before parsing. Every outgoing JavaScript number uses a floating JSON token;
negative zero is `-0.0`. Incoming `-0` and `-0.0` retain their sign. This preserves
binary64 through Python and back. Do not clone or display numeric envelopes using
ordinary JSON.stringify, which erases negative zero; retain the approved exact text.
Stable position sorting keeps duplicate records and equal-position input order,
with +0/-0 equal as sort keys but distinct in bit-exact field binding. Native
serialization is validated again and bound to the actual Registry call snapshot.

Run `node scripts/verify_p1c_runtime.mjs` after building to verify both mounted
11/12 Tool inventories and real Native scenarios. `--config-only` checks config
hashes only. To disable the new Tool, close that session and restart the default
`start-mechanical-dsh.cmd` or restricted eleven-tool headless entry without the
overhung patch. A Profile change does not roll back code, Python project identity,
Plugin version or already-running sessions. See [setup and full v0.2 rollback](../README.md#returning-to-released-v020)
for separate-checkout, environment, configuration backup and runtime checks.

## Python workflow and engineering gates

Run the fixed adapter from the repository with `PYTHONPATH=src`:

```text
python -m mechanical_agent.bridge.overhung_two_plane_workflow_adapter
```

It reads one JSON request from stdin (maximum 16,384 UTF-8 bytes), with no command arguments. The Adapter and Native boundary allow at most 128 raw load records across both planes, counting duplicates, zero and cancelling records. The direct public Workflow/Calculator APIs retain their existing uncapped contracts:

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
module. This bound-review API creates a private full snapshot, runs the same
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

## Execution and resource boundary

The 14B-1 exact rational arithmetic and binary64 rounding contract are unchanged.
The existing approximately O(n²) calculation and independent review remain bounded
by the Native input contract and execution budget; no algorithm optimization or
new engineering acceptance tolerance is introduced here.

The Windows x64 Supervisor creates its launcher suspended with atomic Job-list
association, verifies membership before resume, and manages launcher/runner/Python
descendants. It sets and reads back 256 MiB per-process and 512 MiB aggregate Job
committed-memory quotas, 16 associated processes and KILL_ON_JOB_CLOSE. The old
three Native Tools keep their independent Bridge, Schema and 20-second Native
configuration; they do not use the new shared execution slot.

The single 15-second monotonic execution deadline starts before new-entry argument
inspection. Resolution, all probes, computation, transport, validation and Native
serialization consume it. Probe is additionally capped at 5 seconds and Compute
at 10 seconds. There is exactly one additional recovery window <=3 seconds, shared
by cancellation, timeout, abnormal exit and cleanup. The new Native cooperative
timeout is 18 seconds to accommodate that original recovery window; it does not
create another execution allowance. Host phase grants and original phase deadlines
prevent delayed messages from renewing a phase budget.

RESOURCE_BUSY rejects concurrent admission. TIMEOUT discards late success.
Unconfirmed Job emptiness, handle finalization or recovery fails closed with
REAP_FAILED and BLOCKED; new work is refused until explicit verified recovery.
Successful output requires the complete P1A validation, original request binding,
Job emptiness and handle closure. Failures expose no success results/lineage or raw
tracebacks, paths and environment diagnostics. Missing isolation has no weaker fallback.

Approved resource boundary B does not promise that every instantaneous memory peak
is absolutely below 512 MiB. The quotas concern committed memory; DSH Host is outside
the managed Job. Job Objects are process-tree governance, not a complete malicious-code
sandbox against same-user injection or service-mediated creation.

Approved Host boundary C assumes a continuously responsive trusted Host, normal OS
scheduling and native calls that return. DSH outer argument snapshot/schema work
precedes the plugin clock and may already hold a large string. rc.2 has no maxLength
keyword. That work, final Registry materialization and synchronous Host operations
are not independently preempted by the Supervisor's software deadline. Elapsed time
is checked when synchronous work returns. No hard real-time or whole-Host memory
bound is claimed.

## Reproduction and support scope

Required: Windows x64, Node >=24, Python >=3.12, working creation-time Job-list and
nested Jobs, installed DSH/DSH Tools/Win32 provider 0.2.0-rc.2 and Koffi 3.1.1.
The verified local environment is Windows 11 x64 10.0.26200, Node 24.18.0, Python
3.14.6, pytest 9.0.3 and Schemastery 3.18.4. Both runtime probes require Python
project identity 0.3.0 and retain their source checks; a mismatched identity is an
environment compatibility failure. Reproduction uses a clean source copy and an
existing dependency cache, with no install/upgrade. Fresh-machine installation,
all Windows variants and minimum-version compatibility have not been proved.
The complete dependency tree is not locked; source Registry data must remain available.
No local project reinstall was performed: installed distribution metadata may still
describe an older installation. The source-based runtime probes use the selected
checkout's project version and module path; this is not a packaged-install check.

Build and run the existing safe acceptance entries:

```powershell
node packages/dsh-mechanical-plugin/scripts/build.mjs
node scripts/verify_v15_runtime.mjs
node scripts/verify_p1c_runtime.mjs
```

V1.5 retains old engineering/profile, Python, Plugin and V1 Golden checks. It forces
nine precise memory-pressure skips, checks the reviewed Supervisor test-entry
fingerprint before execution and validates the actual skipped names and TAP counts
afterward. All remaining Plugin tests execute sequentially. Bare npm test does not
provide that default safety policy. The nine skipped scenarios are a1-memory,
memory-counters, memory-study-1/8/32-parallel, memory-study-1/8/32-serial and
memory-native-attempt. They are unexecuted, never reported as passed. Entry/list
drift fails for review before tests; pressure experiments still require separate
authorization, independent outer Jobs, memory limits and time limits.

Existing dedicated fault/DSH scenarios use disposable copies, an independent 1 GiB
outer Job (512 MiB per process, 32 processes), a 25-second wall guard and a 30-second
subprocess timeout, and must confirm EXTERNAL_JOB_EMPTY. The 8-second inventory
threshold is unchanged. These test boundaries do not expand the production budget.
