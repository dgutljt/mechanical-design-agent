# Phase 14C-P1A: input contract and transport boundary

Implementation candidate for independent review; this document does not declare
technical PASS. No twelfth Native Tool is registered. The existing 11 Tool policy,
three engineering registrations, DSH 0.2.0-rc.2 dependencies, Calculator algorithms,
Reviewer algorithms and public Workflow numeric contract remain unchanged.

## Independent TypeScript preflight

`packages/dsh-mechanical-plugin/src/contracts/overhung-input.ts` exports
`preflightOverhungInput(args)` for the future entry. It accepts exactly:

* `power_kw`, `speed_rpm`, `support_span_mm`, `left_overhang_mm`, `right_overhang_mm`
* `plane_1_loads`, `plane_2_loads` (dense arrays of `{load_n, position_mm}`)
* `allowable_shear_mpa`, `assume_constant_torque_over_shaft`

Every numeric input must be a finite JavaScript number. Confirmation must be boolean
`true`. Extra/missing fields, non-JSON types, sparse arrays, custom prototypes,
accessors, Proxies, symbols and encoding hooks are rejected. Each plane and both planes
combined are limited to 128 **raw records**. Empty planes are allowed; duplicates,
zero loads and opposite forces are counted without merging or cancellation.

Geometry mirrors the existing Python model: positive support span, nonnegative
overhangs with at least one positive, finite shaft end and overall length, load
positions within `[-left_overhang_mm, support_span_mm + right_overhang_mm]`.
Power is nonnegative, speed and allowable shear positive. Screening assumptions
and engineering limitations in `VERIFIED_OVERHUNG_SHAFT_WORKFLOW.md` still apply.
Finite inputs may still produce a classified computation/Reviewer failure; the TS
preflight does not perform engineering arithmetic or replace the Python gates.

Execution order required of the future entry:

1. Validate raw fields/types, raw counts and engineering geometry/ranges.
2. Encode the **complete** fixed `{contract_version:"1", operation, input}` envelope
   with the signed-zero codec. Operation is the fixed Workflow ID
   `verified_overhung_two_plane_shaft_strength_chain_v1`.
3. Require encoded UTF-8 size <= 16,384 bytes (inclusive).
4. Only after preflight returns may trusted interpreter resolution, probe and the
   fixed Adapter computation start.

Before inspecting any caller object, `node:util.types.isProxy()` rejects ordinary,
callable and revoked Proxies without invoking traps. This check precedes prototype
inspection, enumeration, descriptors, property reads and serialization at every
nested object/array. Only enumerable own **data descriptors** are copied into a
private, deeply frozen snapshot; getters/setters and custom prototypes are rejected.
The encoder reads this trusted snapshot rather than caller objects. Node v24.18.0
and the built JS modules were tested with independent trap/getter counters of zero.

The returned payload is an immutable string snapshot; future callers must send
that payload rather than re-encoding caller-owned arguments with JSON.stringify.
`preflightOverhungEnvelope(text)` independently bounds the **original** UTF-8
envelope, parses and validates it, then canonicalizes all numeric floating tokens and
bounds the outgoing bytes again. It permits ordinary JSON whitespace, with the
whitespace counted in the original limit. `guardOverhungEnvelopeBytes` is the same
byte guard used by both entry preparations.

`overhung-boundaries.test.mjs` has a deliberately isolated test entry composing
these helpers with the existing `resolvePython`/`run` functions. Rejected requests
produce zero calls to resolveExecutable, probe spawn or computation spawn. A valid
request produces `resolve -> probe -> compute`. This is **test composition only**;
it does not protect an already connected new Native route. P1B supervision/resource
isolation and P1C registration/schema/runtime integration remain separate work.

## Independent Python Adapter boundary

`overhung_two_plane_workflow_adapter.process()` checks list containers, each plane's
raw count and the combined raw count before invoking the Verified Workflow. A
129-record request below the stdin byte cap is therefore rejected through both
`process()` and CLI. Malformed shapes/numbers are still checked by the existing
Workflow before Calculator invocation. Failures contain no engineering results
or success lineage.

CLI retains the existing read of `MAX_INPUT_BYTES + 1` and rejects over 16,384 bytes
**before JSON parsing or Workflow invocation**. Exact 16,384-byte valid JSON with
trailing whitespace is accepted; 16,385 bytes is rejected. Direct public Workflow,
Calculator and Reviewer APIs have no new load cap. A regression calls the public
Workflow directly with 129 records and obtains PASS.

## Signed-zero compatibility

No protocol version change, sidecar fields, string-number tags or public numeric
algorithm changes are needed. `encodeSignedZeroJson` emits negative zero as the
standard JSON **number** `-0.0`. Emitting `-0` would be insufficient: Python's JSON
parser treats it as integer zero. **Every JavaScript number is encoded as a floating
JSON token**, retaining the shortest round-trip decimal and appending `.0` whenever
that decimal has neither a decimal point nor an exponent. Python therefore parses
all numeric fields as `float`, never as an arbitrary-precision `int`. This preserves
binary64 semantics even for unsafe integral doubles whose shortest decimal is not
the exact integer represented by their bits. No old Tool codec is changed.

For example, JS `1000000000000000100` represents integer `1000000000000000128`.
The new token is `1000000000000000100.0`, which Python rounds to precisely the JS
binary64 value. The old bare token still reproduces `LINEAGE_ERROR` when used for
allowable shear; the dedicated codec produces a successful unchanged Workflow.
An independent Python oracle checks both decoded `float` type and packed big-endian
binary64 bytes against original JS bits for safe-integer edges, unsafe integral
doubles, scientific notation, extrema, ULPs, subnormals and negative zero, plus 1,024
deterministically generated bit patterns (non-finite patterns excluded).
The codec never invokes `toJSON`, accessors or Proxy traps.

| Boundary | Behavior |
| --- | --- |
| JS arguments | Detect sign with `Object.is(value, -0)` |
| TS complete envelope | Emit numeric `-0.0`; measure UTF-8 bytes after encoding |
| Python JSON parsing | Existing parser returns negative binary64 zero |
| Verified Workflow | Existing snapshot, bound review and exact handoff checks retain bits |
| Python output | Existing `json.dumps(..., allow_nan=False)` emits `-0.0` |
| Future Native transport helper | `JSON.parse` retains sign; `Object.is` verifies numeric lineage |
| Future display helper | Signed-zero codec emits numeric `-0.0` again |

`overhung-output.ts` provides unregistered response decoding, transport/lineage
validation and text rendering helpers for this chain. All success object layers have
closed, complete required-field shapes: three primary results, both nested planes,
load/station/segment/region records, all review gates, full lineage, four required
model cards and their sources. Validation pins model/Workflow identities, public
units, criterion, Calculator module/function/source mappings and nested plane
parent/field/component relationships. It checks finite numeric types and valid
ranges, matching geometry, copied station/segment data and bit-exact lineage. It
rejects missing/unknown fields and contradictory nested status information.

The public metadata whitelist is currently **empty**: only `{}` is accepted.
Unknown paths, environment information and test diagnostics are rejected rather
than displayed. Failure responses have closed fields and error-code vocabulary;
raw `error.message` text is replaced by fixed public messages before either decoding
returns a result or rendering emits text. Unknown diagnostic fields/details,
traceback containers, metadata and success `results`/`lineage` in failures are
rejected. This prevents raw traceback/path/environment strings from being exposed.
`renderOverhungResponse` exclusively encodes the validated private snapshot; it
cannot bypass validation or render subsequently mutated caller data. Non-string
response payloads are rejected without coercion.

These are structure, identity, range and copied-data checks. No equilibrium,
bending/torque or diameter equation is recomputed. The helpers do not independently
certify engineering correctness or constitute P1C's mounted Native acceptance.
Do not pass these results through JSON.stringify for display or cloning: that
would erase signed zero again. Existing Tools retain their existing protocols and
renderers; no preservation claim is made for those legacy paths.

The end-to-end test sends actual JS negative zero through the production TS codec,
actual fixed Python CLI Adapter, Verified Workflow, Python output parser and the
future response/render helpers. It checks power/torque, load force/position,
overhang geometry, Combined torque and lineage bit identity, plus a subnormal case
whose signed bending component rounds to negative zero. It rejects forged positive
zero in lineage. Adjacent `1 + Number.EPSILON`, smallest positive/negative subnormals
and positive/negative maximum finite loads are preserved. Extreme input values that
overflow the unchanged engineering computation fail without results/lineage.

## Reproducible verification

From the repository root (use an installed Python >= 3.12):

```powershell
$env:PYTHONPATH = 'src'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
python -m pytest
node packages/dsh-mechanical-plugin/scripts/build.mjs
# If python is not on PATH, set MECHANICAL_AGENT_TEST_PYTHON to its absolute path.
npm test --prefix packages/dsh-mechanical-plugin
python examples/v1-shaft-analysis/run_demo.py --verify
```

Boundary tests cover 128/0, 0/128, 127/1, 1/127, 64/64, zero planes,
129 per-plane/combined overflow, exact UTF-8 16,384/16,385, simultaneous count/byte
overflow, Unicode, duplicates, zero/cancelling loads, strict fields/types/nonfinite
values and no-success failure envelopes. Padded valid envelope tests exercise the
byte guard independently: ordinary compact 128-record JS envelopes cannot grow to
16,384 bytes with the fixed numeric-only input shape. No padding field is introduced
into the production input contract.

## Local verification record after targeted repairs (2026-10-15, Asia/Shanghai)

* Python 3.14.6: full `pytest -q` completed with **853 passed**, including **48 new
  Adapter boundary cases** and all 805 existing cases.
* Node v24.18.0: plugin build completed; full plugin suite **59 passed**, no failures
  or skipped tests (20 existing tests plus 39 contract/transport tests).
* Existing V1 demo `--verify` completed successfully.
* 128-record splits 128/0, 0/128, 127/1, 1/127 and 64/64 accepted by TS preflight and
  actual Python Adapter. 129-record per-plane and combined overflows rejected.
* Original full envelope of exactly 16,384 UTF-8 bytes accepted by TS text preflight
  and actual Python stdin; 16,385 bytes rejected. Simultaneous count/byte overflow,
  malformed input and Unicode byte overflow rejected with no success results.
* Isolated TS entry observed zero executable-resolution/probe/computation calls for
  rejected requests and `resolve -> probe -> compute` for a valid request.
* Actual DSH reports 0.2.0-rc.2. A read-only runtime inventory session returned exactly
  the pinned 11 Tool names and the existing base/headless bundles, with no engineering
  invocation. The three engineering registrations remain unchanged.
* `git diff --check` completed without whitespace errors. Protected source, profile,
  inventory, dependencies, knowledge and Golden paths have no tracked diff.
* Branch remains `master`, HEAD `5500852e1dac22ba439b8b48799efa3799ea35b5`.
  Changes are deliberately uncommitted: two modified files, five new files.

The targeted repair touched only the existing input module, output module, Plugin
test file and this contract document. The Adapter, Python boundary test and build
script retain the first candidate's changes. No eighth file or additional execution
report was created.

All three minimal reproductions were exercised. The test file contains 13 named
illegal success-response variants, plus independent deletion of every required
object field, unknown-field insertion at every object layer, unit/source/geometry
and lineage mismatches, failure leakage tests and Proxy/accessor adversarial cases.
Rejected input cases still cause zero interpreter-resolution/probe/computation calls.

The first independent review rejected the candidate for P2-A/B/C. These fixes and
local test observations await independent reacceptance; they are not a technical
PASS verdict or a claim of connected Native enforcement. Submit the unchanged
seven-file scope to the independent Reviewer. No Commit/Push/Tag/Release was run.