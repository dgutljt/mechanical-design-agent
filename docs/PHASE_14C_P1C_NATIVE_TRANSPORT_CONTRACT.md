# Phase 14C-P1C: explicit Native string transport contract

Candidate implementation for independent technical review. This document does not
declare P1C PASS. No Commit, Push, Tag or Release is authorized by this document.

## Registration and profiles

The fixed Native ID is the existing P1A OPERATION / Python WORKFLOW_ID:
`verified_overhung_two_plane_shaft_strength_chain_v1`. Its implementation is
`src/overhung-native.ts`, imported only by the explicit
`.dsh/mechanical-overhung.patch.yml`. Missing/false/invalid opt-in, missing patch
or failed plugin load is a startup error, with no fallback.

The legacy index, Bridge, three old Native Tools and eleven-tool patch/policy
remain unchanged. Both profiles use rc.2 base/headless bundles. The new profile
adds only this one tool; all sixteen existing disabled capability entries remain
identical. The separate headless launcher uses a fresh DSH_HOME and no port. It verifies the
configuration, reads one task, then passes task text as a separate argv value with
shell:false and option terminators for both rc.2 CLI layers. Empty input/EOF
cancels without a model request.

Pinned effective config SHA-256:
* Legacy: `e9b7b1be116bad10696526c20c8a8f719539dbdef09eec97732ab99d6dcee809`.
* Explicit twelve: `34705c05476f7224b8763b6220475fe8932a09dd09c44c00bb1e0d12ddcb6e79`.

## Approved P1C-B carrier

The new tool's closed outer input is exactly `{request_json: string}`.
Its closed outer output is exactly `{response_json: string}`.
The inner JSON text is the complete existing P1A numeric request/response envelope.
No string-number tags, sidecars, replacement mechanics or alternate engineering
schema are introduced. A response carrier is not an engineering success: consumers
must inspect the inner `ok`, `error`, reviews, provenance and lineage.

Example request_json text (the outer DSH call quotes this entire text as a string):

```json
{"contract_version":"1","operation":"verified_overhung_two_plane_shaft_strength_chain_v1","input":{"power_kw":5.5,"speed_rpm":960,"support_span_mm":600,"left_overhang_mm":100,"right_overhang_mm":100,"plane_1_loads":[{"load_n":-1000,"position_mm":-100}],"plane_2_loads":[{"load_n":500,"position_mm":700}],"allowable_shear_mpa":40,"assume_constant_torque_over_shaft":true}}
```

The actual rc.2 dsh-util-values rejects negative zero before Native dispatch and
again when snapshotting numerical output. Only this newly approved string carrier
crosses that restriction. Installed DSH/dependencies and old schemas are untouched.

## One clock and one validation chain

Both public Supervisor APIs immediately enter the same private executeEntry.
It records the original monotonic 15,000 ms deadline before inspecting arguments,
extracting request_json, checking bytes, scanning or parsing. It exposes no
caller-supplied clock, backend, resource limit, module or runner override.

The string path first uses a constant-time UTF-16 length rejection when possible,
then checks the original inner UTF-8 envelope <=16,384 bytes before scanning/parsing.
An iterative lexical gate rejects repeated decoded property keys at every object
scope, including Unicode escape aliases. Existing JSON.parse is the grammar
authority. Trailing data, malformed numbers and nonfinite parsed numbers fail the
unchanged P1A preflight. Existing preflight independently checks all fields, types,
geometry, aggregate 128 raw records, signed-zero and the canonical outgoing bytes.

The raw object path retains its descriptor/Proxy/array guards and P1A preflight.
Both paths send the approved immutable canonical numeric payload, never ordinary
JSON.stringify of engineering numbers. Bare integer text is canonicalized to
floating JSON tokens exactly as P1A already requires; unsafe integral doubles,
subnormals and signed zero keep binary64 semantics. Quoted engineering numbers,
NaN, Infinity and overflow to nonfinite values are rejected.

Only P1B launches the fixed Adapter, following resolve -> probe -> compute.
The unchanged Python Workflow owns Calculator execution, bound Reviewer checks,
four-model Registry provenance, request snapshot and exact Verified Handoff.
The host checks full P1A output, duplicate keys and request binding. Each plane's
trusted input comparison array is stably sorted by finite position ascending using
relational comparisons, with +0/-0 equal as Python sort keys. Equal-position input
order is retained. The original snapshot and untrusted output are never reordered.
Corresponding loads/positions still require Object.is.

Native output serialization remains inside the original deadline. It first
validates through P1A, uses the approved signed-zero codec, parses/validates again,
and compares every field recursively with Object.is at numerical leaves. Field
loss, negative-zero replacement and other serialization defects fail closed as
OUTPUT_INVALID (or the already established timeout/cancellation). Failure fallback
encoding uses only a fixed validated failure envelope with no engineering numbers,
raw stderr, traceback, paths or environment.

The execution slot protects the managed Job and its P1A acceptance. Full P1A
validation/request binding, Job emptiness and handle closure precede slot reuse.
Final carrier materialization after that resource release creates no Job/handle
and remains under the original execution deadline; the slot does not promise
exclusive Host postprocessing for the entire API call.

The Adapter binds the exact approved response string to the Registry's private
arguments snapshot using weak keys. Its renderer only emits that exact string; an
unbound or changed projection fails. It does not reparse or validate engineering
data outside the execution budget. No call cache retains completed arguments.

## Resource and public failure contract

All P1B limits remain: 256 MiB process / 512 MiB managed Job committed-memory
quotas, 16 associated processes, 15 s unified execution, probe <=5 s, compute <=10 s,
and the sole <=3 s recovery window. The Native cooperative timeout is 18 s to
allow that original recovery window; it does not extend the Supervisor budget.
REAP_FAILED/BLOCKED and explicit verified recovery remain mandatory. Classified
failures contain no successful results or lineage. Real Registry cancellation
retains its rc.2 ABORTED outer failure; actual Supervisor CANCELLED is separately
observed, with no successful carrier exposed.

Approved resource B and Host C remain applicable. Job quota configuration/readback
and allocation denial do not imply a hard instantaneous peak guarantee. DSH Host
is outside the 512 MiB engineering Job. No new peak or allocation-denial measurement
is claimed by this phase when the nine pressure scenarios are skipped.

rc.2's supported Native schema subset has no maxLength keyword. Its outer argument
snapshot/schema processing occurs before the plugin-owned clock and may already
hold a large string. Final Registry string materialization is also Host work.
The tool enforces the original inner byte cap on entry, but does not promise an
independently preemptible DSH Host preprocessing or whole-Host memory bound.
Synchronous scanning/validation/serialization observe expiry after returning,
under the already approved continuously responsive Host/normal OS/native-return
assumptions. No stronger real-time guarantee is claimed.

## Reproduction and isolated fault tests

No dependencies need installing. Build with:
`node packages/dsh-mechanical-plugin/scripts/build.mjs`.
Set MECHANICAL_AGENT_TEST_PYTHON to an existing absolute Python >=3.12 path.
Run `node scripts/verify_p1c_runtime.mjs` for real rc.2 CLI/profile/Native checks.
Run `node scripts/verify_p1c_runtime.mjs --config-only` for pinned effective
configuration checks before the explicit launcher starts.

Plugin full non-pressure regression:
```powershell
$env:MECHANICAL_SUPERVISOR_SKIP_MEMORY_PRESSURE = '1'
node --test --test-concurrency=1 packages/dsh-mechanical-plugin/test/*.test.mjs
```

Each resource/fault scenario has its independent 1 GiB outer Job, 512 MiB per
process, 32 processes, 25 s wall guard and 30 s subprocess timeout. Every completed
scenario must confirm EXTERNAL_JOB_EMPTY. DSH scenarios use fresh homes, open stdin
and no model/provider request or listening port; actual mounted ToolRuntime dispatch
executes the Native Tool. Inventory retains its historical 8 s threshold.
Faults patch only disposable built/Python repository copies. Parse/serialization
delay tests shorten deadlines only in disposable copies; real 15 s total and
10 s Python-compute cutoffs are separately exercised.

Tests cover raw/string/Native parity; both -0 and -0.0; computed output -0;
Object.is distinctions; stable duplicates in both planes; adjacent and unsafe
binary64 values; duplicate/escaped keys, invalid numeric text, tails, exact byte
edges, full Reviewer object binding, provenance/lineage pollution, response
serialization loss, cancellation/busy/timeout/reap/blocked, and no weaker runner.
Nine allocation-pressure scenarios are explicitly excluded, never reported passed.
