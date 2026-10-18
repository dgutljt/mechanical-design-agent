import assert from 'node:assert/strict';
import { test } from 'node:test';
import { spawnSync } from 'node:child_process';
import { join, resolve } from 'node:path';
import { readFileSync } from 'node:fs';
import { preflightOverhungInput, preflightOverhungEnvelope, encodeSignedZeroJson,
  guardOverhungEnvelopeBytes, OverhungInputError, OPERATION } from '../dist/contracts/overhung-input.js';
import { decodeOverhungResponse, validateOverhungResponse, renderOverhungResponse } from '../dist/contracts/overhung-output.js';
import { resolvePython, run } from '../dist/bridge/python.js';
import { apply } from '../dist/index.js';

const root = resolve(import.meta.dirname, '../../../');
const python = process.env.MECHANICAL_AGENT_TEST_PYTHON || process.env.MECHANICAL_AGENT_PYTHON || 'python';
const input = { power_kw: 5.5, speed_rpm: 960, support_span_mm: 600,
  left_overhang_mm: 100, right_overhang_mm: 100, plane_1_loads: [], plane_2_loads: [],
  allowable_shear_mpa: 40, assume_constant_torque_over_shaft: true };
const config = { repositoryRoot: root, pythonExecutable: 'C:/mock/python.exe' };
function loads(a, b) {
  return { ...input, plane_1_loads: Array.from({ length: a }, (_, i) => ({ load_n: i % 2 ? -1 : 1, position_mm: 0 })),
    plane_2_loads: Array.from({ length: b }, () => ({ load_n: 0, position_mm: 0 })) };
}
const envelope = x => ({ contract_version: '1', operation: OPERATION, input: x });
const invalid = f => assert.throws(f, e => e instanceof OverhungInputError && e.code === 'INVALID_TOOL_INPUT');
function noSuccess(value) {
  assert.equal(value.ok, false);
  assert.equal('results' in value, false); assert.equal('lineage' in value, false);
}

// ISOLATED TEST HARNESS ONLY. No new call function is mounted by index.ts.
// The harness composes the production preflight with existing resolution/probe
// and fixed-adapter run, without adding supervision or concurrency behavior.
async function isolatedEntry(ctx, value, encoded = false) {
  let prepared;
  try { prepared = encoded ? preflightOverhungEnvelope(value) : preflightOverhungInput(value); }
  catch (e) { return { ok: false, error: { code: e.code } }; }
  const signal = new AbortController().signal;
  const executable = await resolvePython(ctx, config, root, signal);
  return run(ctx, executable, root, [], prepared.payload, signal, 10000,
    'mechanical_agent.bridge.overhung_two_plane_workflow_adapter');
}
function mockRuntime() {
  const calls = [];
  const ctx = { subprocess: {
    async resolveExecutable(candidate) { calls.push('resolve'); return candidate; },
    spawn(spec) {
      calls.push(spec.argv.includes('--probe') ? 'probe' : 'compute');
      const stdout = spec.argv.includes('--probe') ? JSON.stringify({ contract_version: '1', ok: true,
        python_version: [3, 12, 0], python_project_version: '0.3.0', registry_reachable: true,
        module_source: join(root, 'src/mechanical_agent/bridge/torque_adapter.py') }) : '{}';
      return { done: Promise.resolve({ exitCode: 0 }), terminate() {}, async waitForExit() { return true; },
        collected: { stdout: { readFrom: () => ({ text: stdout, lossy: false }) },
          stderr: { readFrom: () => ({ text: '', lossy: false }) } } };
    }
  } };
  return { ctx, calls };
}

test('128 raw records accepted across all required plane splits; empty planes allowed', () => {
  for (const [a, b] of [[128, 0], [0, 128], [127, 1], [1, 127], [64, 64], [0, 0]]) {
    const p = preflightOverhungInput(loads(a, b));
    assert.equal(p.request.input.plane_1_loads.length, a);
    assert.equal(p.request.input.plane_2_loads.length, b);
    assert.ok(Buffer.byteLength(p.payload) <= 16384);
  }
});

test('129 records rejected without merging repeats, zeros or opposing loads', () => {
  for (const [a, b] of [[129, 0], [0, 129], [128, 1], [1, 128], [65, 64], [64, 65], [128, 128]]) {
    invalid(() => preflightOverhungInput(loads(a, b)));
  }
});

test('complete envelope exact 16384/16385 UTF-8 boundaries', () => {
  const text = encodeSignedZeroJson(envelope(loads(128, 0)));
  const atLimit = text + ' '.repeat(16384 - Buffer.byteLength(text));
  assert.equal(Buffer.byteLength(atLimit), 16384);
  assert.equal(preflightOverhungEnvelope(atLimit).request.input.plane_1_loads.length, 128);
  invalid(() => preflightOverhungEnvelope(atLimit + ' '));
  invalid(() => guardOverhungEnvelopeBytes(atLimit + ' '));
});

test('byte limit uses UTF-8, including Unicode rather than JS string length', () => {
  const text = encodeSignedZeroJson(envelope({ ...input, command: '中'.repeat(5500) }));
  assert.ok(text.length < 16384 && Buffer.byteLength(text, 'utf8') > 16384);
  invalid(() => guardOverhungEnvelopeBytes(text));
  invalid(() => preflightOverhungEnvelope(text));
  invalid(() => preflightOverhungInput({ ...input, command: '中' }));
  const unicode = encodeSignedZeroJson({ text: '中😀é' });
  assert.equal(JSON.parse(unicode).text, '中😀é');
  assert.ok(Buffer.byteLength(unicode) > unicode.length);
});

test('raw schema rejects forged fields, types, nonfinite numbers and missing fields', () => {
  for (const [key, value] of [['torque_nm', 0], ['bending_moment_nm', 0], ['min_diameter_mm', 0],
    ['reviews', { torque: 'PASS' }], ['lineage', {}], ['tool_path', 'x'], ['command', 'python'],
    ['pythonExecutable', 'x'], ['power_kw', true], ['speed_rpm', '960'], ['power_kw', NaN],
    ['power_kw', Infinity], ['power_kw', -Infinity], ['power_kw', null], ['power_kw', 1n],
    ['assume_constant_torque_over_shaft', 1], ['assume_constant_torque_over_shaft', false],
    ['plane_1_loads', {}], ['plane_2_loads', null]]) invalid(() => preflightOverhungInput({ ...input, [key]: value }));
  for (const value of [null, [], true, {}, { ...input, plane_1_loads: [{ load_n: 1, position_mm: 0, extra: 1 }] },
    { ...input, plane_1_loads: [{ load_n: false, position_mm: 0 }] },
    { ...input, plane_1_loads: [{ load_n: 1, position_mm: NaN }] },
    { ...input, plane_1_loads: [null] }, { ...input, plane_1_loads: new Array(1) }]) invalid(() => preflightOverhungInput(value));
  const missing = { ...input }; delete missing.power_kw;
  invalid(() => preflightOverhungInput(missing));
});

test('JSON encoding rejects hidden fields, symbols, accessors, hooks and custom arrays', () => {
  const getter = { ...input }; Object.defineProperty(getter, 'power_kw', { enumerable: true, get() { assert.fail('getter ran'); } });
  const hidden = { ...input }; Object.defineProperty(hidden, 'command', { value: 'x' });
  const symbol = { ...input, [Symbol('command')]: 1 };
  const hook = { ...input, toJSON() { assert.fail('hook ran'); } };
  const custom = Object.assign(Object.create({ command: 'x' }), input);
  const array = []; array.command = 'x';
  for (const value of [getter, hidden, symbol, hook, custom, { ...input, plane_1_loads: array }]) invalid(() => preflightOverhungInput(value));
  const cyclic = {}; cyclic.self = cyclic;
  invalid(() => encodeSignedZeroJson(cyclic));
  invalid(() => encodeSignedZeroJson({ x: undefined }));
});

test('existing geometry and engineering applicability preserved', () => {
  for (const update of [{ power_kw: -1 }, { speed_rpm: 0 }, { allowable_shear_mpa: 0 },
    { support_span_mm: 0 }, { left_overhang_mm: -1 }, { right_overhang_mm: -1 },
    { left_overhang_mm: 0, right_overhang_mm: 0 },
    { support_span_mm: Number.MAX_VALUE, right_overhang_mm: Number.MAX_VALUE },
    { support_span_mm: Number.MAX_VALUE, left_overhang_mm: Number.MAX_VALUE },
    { plane_1_loads: [{ load_n: 0, position_mm: -100.00000000000001 }] },
    { plane_2_loads: [{ load_n: 0, position_mm: 700.0000000000001 }] }]) invalid(() => preflightOverhungInput({ ...input, ...update }));
});

test('all rejections precede interpreter resolution, probe and calculation in isolated entry', async () => {
  const exact = encodeSignedZeroJson(envelope(input));
  const both = encodeSignedZeroJson(envelope(loads(129, 0))).padEnd(16385, ' ');
  for (const [value, encoded] of [[loads(129, 0), false], [loads(0, 129), false], [loads(65, 64), false],
    [{ ...input, power_kw: NaN }, false], [{ ...input, command: 'x' }, false],
    [{ ...input, support_span_mm: 0 }, false], [{ ...input, assume_constant_torque_over_shaft: 1 }, false],
    [exact.padEnd(16385, ' '), true], [both, true],
    [encodeSignedZeroJson(envelope({ ...input, command: '中'.repeat(5500) })), true],
    ['{"input": NaN}', true], [encodeSignedZeroJson({ ...envelope(input), extra: 0 }), true]]) {
    const { ctx, calls } = mockRuntime();
    const valueOut = await isolatedEntry(ctx, value, encoded);
    noSuccess(valueOut); assert.equal(valueOut.error.code, 'INVALID_TOOL_INPUT');
    assert.deepEqual(calls, []);
  }
  const { ctx, calls } = mockRuntime();
  await isolatedEntry(ctx, loads(64, 64));
  assert.deepEqual(calls, ['resolve', 'probe', 'compute']);
});

test('signed-zero encoder preserves JS binary64 and emits compatible standard JSON', () => {
  assert.equal(JSON.stringify(-0), '0'); // regression trigger
  for (const x of [-0, 0, 1 + Number.EPSILON, Number.MIN_VALUE, -Number.MIN_VALUE,
    Number.MAX_VALUE, -Number.MAX_VALUE]) {
    const p = preflightOverhungInput({ ...input, power_kw: -0, plane_1_loads: [{ load_n: x, position_mm: -0 }] });
    assert.ok(p.payload.includes('"power_kw":-0.0'));
    const parsed = JSON.parse(p.payload);
    assert.ok(Object.is(parsed.input.power_kw, -0));
    assert.ok(Object.is(parsed.input.plane_1_loads[0].load_n, x));
    assert.ok(Object.is(parsed.input.plane_1_loads[0].position_mm, -0));
  }
  const raw = JSON.stringify(envelope(input)).replace('"power_kw":5.5', '"power_kw":-0');
  assert.ok(preflightOverhungEnvelope(raw).payload.includes('"power_kw":-0.0'));
});

function adapterRequest(value) {
  const p = preflightOverhungInput(value);
  const result = spawnSync(python, ['-m', 'mechanical_agent.bridge.overhung_two_plane_workflow_adapter'],
    { cwd: root, input: p.payload, encoding: 'utf8', windowsHide: true,
      env: { ...process.env, PYTHONPATH: join(root, 'src') } });
  assert.ifError(result.error); assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stderr, '');
  return decodeOverhungResponse(result.stdout);
}

test('E2E JS -> TS envelope -> Python -> Verified Workflow -> Native transport validation/render', () => {
  for (const x of [-0, 1 + Number.EPSILON, Number.MIN_VALUE, -Number.MIN_VALUE, Number.MAX_VALUE, -Number.MAX_VALUE]) {
    const value = adapterRequest({ ...input, power_kw: -0, right_overhang_mm: -0,
      plane_1_loads: [{ load_n: x, position_mm: -0 }] });
    assert.equal(value.ok, true);
    const r = value.results;
    assert.ok(Object.is(r.statics.plane_1.loads[0].load_n, x));
    assert.ok(Object.is(r.statics.plane_1.loads[0].position_mm, -0));
    for (const z of [r.torque.power_kw, r.torque.torque_nm, r.combined.torque_nm,
      value.lineage.torque.exact_value, r.statics.right_overhang_mm]) assert.ok(Object.is(z, -0));
    const displayed = decodeOverhungResponse(renderOverhungResponse(value)[0].text);
    assert.ok(Object.is(displayed.lineage.torque.exact_value, -0));
    assert.ok(Object.is(displayed.results.statics.plane_1.loads[0].load_n, x));
    const forged = structuredClone(value); forged.lineage.torque.exact_value = 0;
    assert.throws(() => validateOverhungResponse(forged), /lineage/);
    const ulp = structuredClone(value); ulp.results.combined.torque_nm = Number.MIN_VALUE;
    assert.throws(() => validateOverhungResponse(ulp), /lineage/);
  }
  const value = adapterRequest({ ...input, support_span_mm: 1, left_overhang_mm: 1, right_overhang_mm: 0,
    plane_1_loads: [{ load_n: 2 * Number.MIN_VALUE, position_mm: .5 }] });
  const displayed = decodeOverhungResponse(renderOverhungResponse(value)[0].text);
  const station = displayed.lineage.critical_stations.find(s => s.position_mm === .5);
  assert.ok(Object.is(station.plane_1_moment_nmm, -0));
  const forged = structuredClone(value);
  forged.lineage.critical_stations.find(s => s.position_mm === .5).plane_1_moment_nmm = 0;
  assert.throws(() => validateOverhungResponse(forged), /lineage/);
});

test('finite inputs that overflow calculations fail closed without results or lineage', () => {
  const value = adapterRequest({ ...input, power_kw: Number.MAX_VALUE });
  noSuccess(value);
  assert.equal(value.error.code, 'ENGINEERING_INPUT_ERROR');
  const forged = { ...value, results: {} };
  assert.throws(() => validateOverhungResponse(forged), /failure/);
  assert.throws(() => decodeOverhungResponse('NaN'));
  assert.throws(() => validateOverhungResponse({ ...value, metadata: { x: Infinity } }));
});

test('old three engineering registrations and pinned 11 Tool policy unchanged', () => {
  const registered = []; apply({ tools: { register: tool => registered.push(tool) } }, config);
  assert.deepEqual(registered.map(t => t.name).sort(), ['analyze_verified_shaft_strength',
    'analyze_verified_two_plane_shaft_strength', 'calculate_transmitted_torque']);
  const policy = JSON.parse(readFileSync(join(root, 'scripts/v15-policy.json')));
  assert.equal(policy.restricted.tools.length, 11);
  assert.equal(policy.dshVersion, '0.2.0-rc.2');
});

function doubleBits(value) {
  const bytes = Buffer.alloc(8); bytes.writeDoubleBE(value); return bytes.toString('hex');
}
function pythonJson(command, payload) {
  const result = spawnSync(python, ['-c', command], { cwd: root, input: payload, encoding: 'utf8',
    windowsHide: true, env: { ...process.env, PYTHONPATH: join(root, 'src') } });
  assert.ifError(result.error); assert.equal(result.status, 0, result.stderr); assert.equal(result.stderr, '');
  return JSON.parse(result.stdout);
}

test('P2-A: independent Python decoder preserves binary64 bits AND float type for every JS number', () => {
  const values = [-0, 0, 1, -1, Number.MAX_SAFE_INTEGER - 1, Number.MAX_SAFE_INTEGER,
    Number.MAX_SAFE_INTEGER + 1, Number.MAX_SAFE_INTEGER + 2, -(Number.MAX_SAFE_INTEGER + 1),
    1000000000000000100, -1000000000000000100, 1e20, 1e21, 1e-6, 1e-7,
    Number.MAX_VALUE, -Number.MAX_VALUE, 2.2250738585072014e-308,
    Number.MIN_VALUE, -Number.MIN_VALUE, 2 * Number.MIN_VALUE,
    1 - Number.EPSILON / 2, 1 + Number.EPSILON, 2 ** 53 - 1, 2 ** 53, 2 ** 53 + 2];
  // Independent deterministic binary64 bit corpus, including both signs and
  // many exponents. The Python oracle observes the decoded type and raw bits,
  // not the encoder's decimal spelling or another JS JSON round trip.
  let state = 0x8d36ad72b5c04e19n;
  for (let i = 0; i < 1024; i++) {
    state = (state * 6364136223846793005n + 1442695040888963407n) & ((1n << 64n) - 1n);
    const bytes = Buffer.alloc(8); bytes.writeBigUInt64BE(state);
    const value = bytes.readDoubleBE(); if (Number.isFinite(value)) values.push(value);
  }
  const decoded = pythonJson('import json,sys,struct; xs=json.load(sys.stdin); print(json.dumps([[type(x).__name__,struct.pack("!d",x).hex()] for x in xs]))',
    encodeSignedZeroJson(values));
  assert.equal(decoded.length, values.length);
  decoded.forEach(([type, bits], i) => { assert.equal(type, 'float'); assert.equal(bits, doubleBits(values[i]), `index ${i}`); });
  assert.equal(BigInt(1000000000000000100), 1000000000000000128n);
});

test('P2-A: Reviewer integral-double LINEAGE_ERROR reproduction is corrected without Python edits', () => {
  const inputs = { ...input, allowable_shear_mpa: 1000000000000000100 };
  const legacy = pythonJson('import json,sys; from mechanical_agent.bridge.overhung_two_plane_workflow_adapter import process; print(json.dumps(process(json.load(sys.stdin))))',
    JSON.stringify(envelope(inputs)));
  noSuccess(legacy); assert.equal(legacy.error.code, 'LINEAGE_ERROR');
  const repaired = adapterRequest(inputs);
  assert.equal(repaired.ok, true);
  assert.equal(doubleBits(repaired.results.combined.allowable_shear_mpa), doubleBits(inputs.allowable_shear_mpa));
});

test('P2-C: native isProxy works in built Node 24 module before ANY Proxy trap', async () => {
  let traps = 0, getters = 0;
  const target = { ...input };
  Object.defineProperty(target, 'power_kw', { configurable: true, enumerable: true, get() { getters++; return 5.5; } });
  const trapsHandler = {
    get(t, k, r) { traps++; return Reflect.get(t, k, r); },
    ownKeys(t) { traps++; return Reflect.ownKeys(t); },
    getPrototypeOf(t) { traps++; return Reflect.getPrototypeOf(t); },
    getOwnPropertyDescriptor(t, k) {
      traps++;
      if (k === 'power_kw') return { configurable: true, enumerable: true, writable: true, value: 5.5 };
      return Reflect.getOwnPropertyDescriptor(t, k);
    }
  };
  const proxy = new Proxy(target, trapsHandler);
  const { ctx, calls } = mockRuntime();
  noSuccess(await isolatedEntry(ctx, proxy));
  invalid(() => encodeSignedZeroJson(proxy));
  assert.deepEqual(calls, []); assert.equal(traps, 0); assert.equal(getters, 0);
});

test('P2-C: nested load/array/object, callable and revoked Proxies all rejected with zero traps', async () => {
  let traps = 0;
  const handler = { get() { traps++; assert.fail('get trap'); }, ownKeys() { traps++; assert.fail('ownKeys trap'); },
    getPrototypeOf() { traps++; assert.fail('prototype trap'); },
    getOwnPropertyDescriptor() { traps++; assert.fail('descriptor trap'); }, apply() { traps++; assert.fail('apply trap'); } };
  const loadProxy = new Proxy({ load_n: 1, position_mm: 0 }, handler);
  const arrayProxy = new Proxy([], handler);
  const revoked = Proxy.revocable({}, handler); revoked.revoke();
  const values = [new Proxy(input, handler), { ...input, plane_1_loads: arrayProxy },
    { ...input, plane_2_loads: [loadProxy] }, { ...input, plane_1_loads: [loadProxy] },
    { ...input, power_kw: new Proxy(function () {}, handler) },
    { ...input, plane_2_loads: [revoked.proxy] }, { ...input, extra: { child: { proxy: loadProxy } } }];
  for (const value of values) {
    const { ctx, calls } = mockRuntime();
    noSuccess(await isolatedEntry(ctx, value)); invalid(() => encodeSignedZeroJson(value));
    assert.deepEqual(calls, []);
  }
  invalid(() => preflightOverhungInput(revoked.proxy));
  assert.equal(traps, 0);
});

test('P2-C: getter, setter and array accessor execution counts remain zero', async () => {
  let getters = 0, setters = 0;
  const get = () => { getters++; return 1; }, set = () => { setters++; };
  const top = { ...input }; Object.defineProperty(top, 'power_kw', { enumerable: true, get });
  const setter = { ...input }; Object.defineProperty(setter, 'power_kw', { enumerable: true, set });
  const load = { position_mm: 0 }; Object.defineProperty(load, 'load_n', { enumerable: true, get, set });
  const array = []; Object.defineProperty(array, '0', { enumerable: true, configurable: true, get });
  const extra = { ...input, extra: {} }; Object.defineProperty(extra.extra, 'hidden', { enumerable: true, get });
  for (const value of [top, setter, { ...input, plane_1_loads: [load] }, { ...input, plane_2_loads: array }, extra]) {
    const { ctx, calls } = mockRuntime(); noSuccess(await isolatedEntry(ctx, value));
    assert.deepEqual(calls, []); invalid(() => encodeSignedZeroJson(value));
  }
  assert.equal(getters, 0); assert.equal(setters, 0);
});

test('P2-C: validated private descriptor snapshot is detached and frozen at every level', () => {
  const original = { ...input, plane_1_loads: [{ load_n: -0, position_mm: 0 }] };
  const prepared = preflightOverhungInput(original);
  original.plane_1_loads[0].load_n = 50; original.plane_1_loads.push({ load_n: 10, position_mm: 0 });
  assert.ok(Object.is(prepared.request.input.plane_1_loads[0].load_n, -0));
  assert.equal(prepared.request.input.plane_1_loads.length, 1);
  for (const value of [prepared, prepared.request, prepared.request.input, prepared.request.input.plane_1_loads,
    prepared.request.input.plane_1_loads[0]]) assert.equal(Object.isFrozen(value), true);
  assert.throws(() => { prepared.request.input.plane_1_loads[0].load_n = 8; }, TypeError);
  assert.equal(encodeSignedZeroJson(prepared.request), prepared.payload);
});

let validResponse;
function goodResponse() {
  validResponse ??= adapterRequest({ ...input, plane_1_loads: [{ load_n: -1000, position_mm: -100 }],
    plane_2_loads: [{ load_n: 500, position_mm: 700 }] });
  return structuredClone(validResponse);
}
const reviewerVariants = [
  ['missing plane_1', v => { delete v.results.statics.plane_1; }],
  ['wrong nested MODEL_ID', v => { v.results.statics.plane_2.model_id = 'wrong'; }],
  ['incomplete Lineage', v => { delete v.lineage.nested_plane_models; }],
  ['wrong source unit', v => { v.lineage.torque.source_unit = 'N*mm'; }],
  ['null provenance source', v => { v.provenance.transmitted_torque_v1.sources = [null]; }],
  ['nested review FAIL', v => { v.results.statics.plane_1.review = { status: 'FAIL' }; }],
  ['negative diameter', v => { v.results.combined.min_diameter_mm = -1; }],
  ['wrong numeric field type', v => { v.results.torque.power_kw = '5.5'; }],
  ['metadata test environment leak', v => { v.metadata.test_environment = { python: 'C:/private/python.exe', secret: 'ENV_SECRET' }; }],
  ['missing nested model provenance', v => { delete v.provenance.two_support_overhung_signed_point_load_v1; }],
  ['wrong nested parent relationship', v => { v.lineage.nested_plane_models.plane_1.parent_model_id = 'solid_shaft_combined_tresca_v1'; }],
  ['wrong source ID relationship', v => { v.provenance.transmitted_torque_v1.model.source_ids = ['engineering_statics_beam_equilibrium']; }],
  ['wrong Workflow identity', v => { v.workflow_id = 'other_chain'; }]
];
for (const [name, mutate] of reviewerVariants) {
  test(`P2-B Reviewer variant rejected by validation/decoding/rendering: ${name}`, () => {
    const value = goodResponse(); mutate(value);
    assert.throws(() => validateOverhungResponse(value));
    assert.throws(() => decodeOverhungResponse(encodeSignedZeroJson(value)));
    assert.throws(() => renderOverhungResponse(value));
  });
}

function objectPaths(value, path = []) {
  if (!value || typeof value !== 'object') return [];
  const paths = Array.isArray(value) ? [] : [path];
  for (const key of Object.keys(value)) paths.push(...objectPaths(value[key], [...path, key]));
  return paths;
}
function atPath(value, path) { return path.reduce((object, key) => object[key], value); }

test('P2-B: every required field at every object layer is independently required', () => {
  const base = goodResponse();
  for (const path of objectPaths(base)) {
    for (const key of Object.keys(atPath(base, path))) {
      const variant = structuredClone(base); delete atPath(variant, path)[key];
      assert.throws(() => validateOverhungResponse(variant), `accepted missing ${[...path, key].join('.')}`);
    }
  }
});

test('P2-B: unknown fields and contradictory nested statuses rejected at every layer', () => {
  const base = goodResponse();
  for (const path of objectPaths(base)) {
    const variant = structuredClone(base); atPath(variant, path).review_status = 'FAIL';
    assert.throws(() => renderOverhungResponse(variant), `accepted extra field at ${path.join('.')}`);
  }
});

test('P2-B: copied structure, geometry, provenance, units and nested lineage mismatches rejected', () => {
  const variants = [
    v => { v.reviews.statics = 'FAIL'; },
    v => { v.results.statics.plane_1.support_span_mm += 1; },
    v => { v.results.statics.plane_2.loads[0].position_mm = 701; },
    v => { v.results.statics.units.force = 'kN'; },
    v => { v.results.statics.plane_1.units.converted_moment = 'N*mm'; },
    v => { v.lineage.bending_moment.source_field = 'critical_resultant_bending_moment_nmm'; },
    v => { v.lineage.nested_plane_models.plane_2.component = 'M_y'; },
    v => { v.lineage.nested_plane_models.plane_1.result_field = 'statics.plane_2'; },
    v => { v.provenance.two_support_overhung_signed_point_load_v1.model.calculator_function = 'other'; },
    v => { v.provenance.two_support_overhung_two_plane_point_load_v1.sources[0].id = 'other'; },
    v => { v.provenance.two_support_overhung_signed_point_load_v1.sources[0].title = null; },
    v => { v.provenance.solid_shaft_combined_tresca_v1.sources[0].url = 'file:///private/trace'; },
    v => { v.results.statics.resultant_stations[0].position_mm += 1; },
    v => { v.results.statics.plane_1.segments[0].moment_start_nmm += 1; },
    v => { v.results.statics.critical_regions[0].x_end_mm = -101; },
    v => { v.results.statics.critical_stations = []; },
    v => { v.results.combined.allowable_shear_mpa = 0; },
    v => { v.results.combined.torque_nm = -1; },
    v => { v.results.combined.bending_moment_nmm = -1; },
    v => { v.results.statics.critical_resultant_bending_moment_nm = -1; },
    v => { v.assumptions = 'not an array'; },
    v => { v.provenance.transmitted_torque_v1.sources = [true]; },
    v => { v.provenance.transmitted_torque_v1.model.units[0] = 'P_kW: W'; }
  ];
  for (const mutate of variants) { const v = goodResponse(); mutate(v); assert.throws(() => renderOverhungResponse(v)); }
});

test('P2-B: failure diagnostics canonicalized; traceback/path/environment never returned or displayed', () => {
  const failure = { contract_version: '1', operation: OPERATION, ok: false, metadata: {},
    error: { code: 'INTERNAL_ADAPTER_ERROR', message: 'Traceback C:/private/adapter.py ENV_SECRET=private' } };
  const parsed = decodeOverhungResponse(encodeSignedZeroJson(failure)); noSuccess(parsed);
  assert.equal(parsed.error.message, 'Engineering adapter failed.');
  const rendered = renderOverhungResponse(failure)[0].text;
  assert.equal(/Traceback|private|ENV_SECRET/.test(rendered), false);
  noSuccess(JSON.parse(rendered));
  for (const extra of [{ traceback: 'private' }, { results: goodResponse().results }, { lineage: goodResponse().lineage },
    { metadata: { environment: 'ENV_SECRET' } }, { status: 'PASS' }]) assert.throws(() => renderOverhungResponse({ ...failure, ...extra }));
  assert.throws(() => renderOverhungResponse({ ...failure, error: { ...failure.error, details: { path: 'private' } } }));
  assert.throws(() => renderOverhungResponse({ ...failure, error: { code: 'UNRECOGNIZED', message: 'private' } }));
});

test('P2-B/C: response validators and renderer reject Proxy/getter before executing user code', () => {
  let traps = 0, getters = 0;
  const base = goodResponse();
  const proxied = new Proxy(base.results.statics.plane_1, { get() { traps++; assert.fail('get'); },
    ownKeys() { traps++; assert.fail('ownKeys'); }, getOwnPropertyDescriptor() { traps++; assert.fail('descriptor'); } });
  base.results.statics.plane_1 = proxied;
  assert.throws(() => validateOverhungResponse(base)); assert.throws(() => renderOverhungResponse(base));
  const getter = goodResponse(); Object.defineProperty(getter.metadata, 'path', { enumerable: true, get() { getters++; return 'private'; } });
  assert.throws(() => renderOverhungResponse(getter));
  assert.equal(traps, 0); assert.equal(getters, 0);
});

test('P2-B: validated success snapshot remains safe after caller mutation', () => {
  const original = goodResponse(), safe = validateOverhungResponse(original);
  original.metadata.path = 'C:/private'; original.results.combined.min_diameter_mm = -5;
  assert.equal(Object.isFrozen(safe), true);
  assert.equal(Object.isFrozen(safe.results.combined), true);
  const rendered = decodeOverhungResponse(renderOverhungResponse(safe)[0].text);
  assert.equal(rendered.ok, true); assert.ok(rendered.results.combined.min_diameter_mm >= 0);
  assert.deepEqual(Object.keys(rendered.metadata), []);
});

test('P2-A: safe-integer edge, unsafe integral doubles and scientific notation pass actual workflow handoff', () => {
  for (const allowable of [Number.MAX_SAFE_INTEGER - 1, Number.MAX_SAFE_INTEGER, Number.MAX_SAFE_INTEGER + 1,
    Number.MAX_SAFE_INTEGER + 2, 1000000000000000100, 1e20, 1e21, 1 + Number.EPSILON]) {
    const response = adapterRequest({ ...input, allowable_shear_mpa: allowable });
    assert.equal(response.ok, true);
    assert.equal(doubleBits(response.results.combined.allowable_shear_mpa), doubleBits(allowable));
  }
});

test('P2-B/C: decoder rejects non-string payloads without coercion or Proxy traps', () => {
  let hits = 0;
  const proxy = new Proxy({}, { get() { hits++; assert.fail('coercion trap'); } });
  const value = { toString() { hits++; assert.fail('coercion hook'); } };
  for (const payload of [proxy, value, null, 1, []]) assert.throws(() => decodeOverhungResponse(payload));
  assert.equal(hits, 0);
});
