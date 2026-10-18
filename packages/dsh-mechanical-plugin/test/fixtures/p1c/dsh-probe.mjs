// Test-only plugin mounted into an actual rc.2 CLI. No LLM/provider call.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { OPERATION, encodeSignedZeroJson } from '../../../dist/contracts/overhung-input.js';
import { validateOverhungResponse, decodeOverhungResponse } from '../../../dist/contracts/overhung-output.js';
export const name = 'p1c-native-acceptance-probe';
export const inject = ['tools', 'profileContext'];
const root = fileURLToPath(new URL('../../../../../', import.meta.url));
const plugin = fileURLToPath(new URL('../../../', import.meta.url));
const input = { power_kw: 5.5, speed_rpm: 960, support_span_mm: 600,
  left_overhang_mm: 100, right_overhang_mm: 100,
  plane_1_loads: [{ load_n: 500, position_mm: 700 }, { load_n: -1000, position_mm: -100 }],
  plane_2_loads: [{ load_n: 200, position_mm: 600 }, { load_n: -300, position_mm: 0 }],
  allowable_shear_mpa: 40, assume_constant_torque_over_shaft: true };
const emit = (tag, value) => process.stderr.write(tag + ' ' + encodeSignedZeroJson(value) + '\n');
export function apply(ctx) {
  setImmediate(async () => {
    try {
      const mode = process.env.MECHANICAL_P1C_MODE;
      const policy = JSON.parse(readFileSync(join(root, 'scripts/p1c-policy.json'), 'utf8'));
      const legacy = JSON.parse(readFileSync(join(root, 'scripts/v15-policy.json'), 'utf8'));
      const tools = ctx.tools.schemas().map(t => t.name).sort();
      const expected = ['inventory11','legacy11'].includes(mode) ? legacy.allowed.toSorted() : policy.allowed;
      assert.deepEqual(tools, expected);
      assert.deepEqual([...ctx.profileContext.startedBundles].sort(), policy.bundles.toSorted());
      const oldTools = legacy.required.filter(t => t !== 'skill').sort().map(name => {
        const t = ctx.tools.get(name);
        return { name, parameters: t.parameters, output: t.output.schema, timeoutMs: t.timeoutMs };
      });
      const fingerprint = createHash('sha256').update(JSON.stringify(oldTools)).digest('hex');
      emit('P1C_INVENTORY', { tools, bundles: [...ctx.profileContext.startedBundles], legacyToolsSha256: fingerprint,
        legacyTimeouts: oldTools.map(t => t.timeoutMs), mode });
      if (policy.legacyToolsSha256) assert.equal(fingerprint, policy.legacyToolsSha256);
      if (['inventory11','legacy11'].includes(mode)) {
        assert.equal(process[Symbol.for('mechanical-agent.overhung-supervisor.slot.v1')], undefined,
          'default profile loaded the new execution entry');
        assert.equal(ctx.tools.get(OPERATION), undefined);
        if (mode === 'legacy11') {
          const cases = [
            ['calculate_transmitted_torque', { power_kw: 5.5, speed_rpm: 960 }],
            ['analyze_verified_shaft_strength', { power_kw: 5.5, speed_rpm: 960, span_mm: 600,
              loads: [{ load_n: 1000, position_mm: 200 }, { load_n: 500, position_mm: 450 }], allowable_shear_mpa: 40 }],
            ['analyze_verified_two_plane_shaft_strength', { power_kw: 5.5, speed_rpm: 960, span_mm: 600,
              plane_1_loads: [{ load_n: -1000, position_mm: 200 }],
              plane_2_loads: [{ load_n: -1000, position_mm: 400 }], allowable_shear_mpa: 40 }]
          ];
          for (const [name, arguments_] of cases) {
            const result = await ctx.tools.execute({ callId: 'p1c-old-' + name, name,
              arguments: arguments_, signal: new AbortController().signal });
            assert.equal(result.isError, false); assert.equal(result.value.ok, true);
            emit('P1C_LEGACY_NATIVE', { name, ok: result.value.ok });
          }
          assert.equal(process[Symbol.for('mechanical-agent.overhung-supervisor.slot.v1')], undefined);
        }
        emit('P1C_DONE', { mode }); return;
      }
      const mounted = ctx.tools.get(OPERATION);
      assert.deepEqual(Object.keys(mounted.parameters.properties), ['request_json']);
      assert.equal(mounted.parameters.properties.request_json.type, 'string');
      assert.equal(mounted.parameters.additionalProperties, false);
      assert.deepEqual(Object.keys(mounted.output.schema.properties), ['response_json']);
      assert.equal(mounted.output.schema.properties.response_json.type, 'string');
      assert.equal(mounted.output.schema.additionalProperties, false);
      emit('P1C_STRING_SCHEMA', { input: 'request_json:string', output: 'response_json:string' });
      if (mode === 'inventory12') { emit('P1C_DONE', { mode }); return; }
      const bundle = process.env.MECHANICAL_P1C_BUNDLE || join(plugin, 'dist');
      const api = await import(pathToFileURL(join(bundle, 'supervisor/overhung-supervisor.js')));
      const { windowsNative, PROCESS_BYTES, JOB_BYTES } = await import(pathToFileURL(join(bundle, 'supervisor/windows-native.js')));
      const n = windowsNative(), grants = [], jobs = [], children = [];
      const create = n.createJob, spawn = n.spawn, write = n.writeAsync;
      n.createJob = (...args) => {
        const owner = create(...args), limits = n.limits(owner.job);
        assert.equal(limits.processBytes, PROCESS_BYTES); assert.equal(limits.jobBytes, JOB_BYTES);
        assert.equal(limits.flags, 0x2308); jobs.push(limits); return owner;
      };
      n.spawn = (...args) => {
        const child = spawn(...args);
        assert.equal(n.member(child.process, args[3]), true);
        children.push({ member: true, launcher: args[0].at(-1).endsWith('watchdog.js') }); return child;
      };
      let controller, stopScheduled = false;
      n.writeAsync = (handle, text) => {
        const grant = JSON.parse(text); grants.push(grant.phase);
        if (mode === 'cancel' && grant.phase === 'compute' && !stopScheduled) {
          stopScheduled = true; setTimeout(() => controller.abort(), 5);
        }
        return write(handle, text);
      };
      let callId = 0, observed = 0;
      ctx.on('tools/result', (exec, result) => { if (exec.name === OPERATION) observed++; });
      const envelope = (args = input) => encodeSignedZeroJson({ contract_version: '1', operation: OPERATION, input: args });
      const dispatch = (args, c = new AbortController()) => ctx.tools.execute({
        callId: 'p1c-' + (++callId), name: OPERATION, arguments: args, signal: c.signal
      });
      const callText = (text, c) => dispatch({ request_json: text }, c);
      const call = (args = input, c) => callText(envelope(args), c);
      const inner = result => {
        assert.equal(result.isError, false, JSON.stringify(result.error));
        assert.deepEqual(Object.keys(result.value), ['response_json']);
        assert.equal(result.value.response_json, result.content[0].text);
        return decodeOverhungResponse(result.value.response_json);
      };
      const failure = (result, code) => {
        assert.equal(result.isError, false, JSON.stringify(result.error));
        const value = inner(result);
        assert.equal(value.ok, false); assert.equal(value.error.code, code);
        assert.equal('results' in value, false); assert.equal('lineage' in value, false);
        assert.doesNotMatch(encodeSignedZeroJson(result.content), /SECRET_MARKER|Traceback/);
      };
      if (['normal','signed-zero','output-zero','boundary128','ordered','binary64'].includes(mode)) {
        let args = input;
        if (mode === 'signed-zero') args = { ...input, power_kw: -0, left_overhang_mm: -0,
          plane_1_loads: [{ load_n: -0, position_mm: -0 }, { load_n: 0, position_mm: 0 }], plane_2_loads: [] };
        if (mode === 'output-zero') args = { ...input, support_span_mm: 1, left_overhang_mm: 1, right_overhang_mm: 0,
          plane_1_loads: [{ load_n: 2 * Number.MIN_VALUE, position_mm: .5 }], plane_2_loads: [] };
        if (mode === 'binary64') args = { ...input, allowable_shear_mpa: 1000000000000000100 };
        if (mode === 'boundary128') args = { ...input,
          plane_1_loads: Array.from({ length: 64 }, (_, i) => ({ load_n: i % 2 ? -1 : 1, position_mm: 63 - i })),
          plane_2_loads: Array.from({ length: 64 }, (_, i) => ({ load_n: i % 2 ? -2 : 2, position_mm: 600 - i })) };
        const result = await call(args); assert.equal(result.isError, false, JSON.stringify(result.error));
        const value = inner(result); assert.equal(value.ok, true);
        assert.equal(encodeSignedZeroJson(JSON.parse(result.content[0].text)), encodeSignedZeroJson(value));
        assert.equal(Object.keys(value.provenance).length, 4);
        assert.ok(Object.values(value.reviews).every(x => x === 'PASS'));
        if (mode === 'signed-zero') {
          assert.ok(Object.is(value.results.torque.power_kw, -0));
          assert.ok(Object.is(value.results.statics.plane_1.loads[1].load_n, +0));
          assert.equal(Object.is(value.results.statics.plane_1.loads[1].load_n, -0), false);
          assert.ok(Object.is(value.lineage.torque.exact_value, -0));
          assert.ok(Object.is(JSON.parse(result.content[0].text).results.statics.plane_1.loads[0].position_mm, -0));
        }
        if (mode === 'signed-zero') {
          const lexical = envelope(args).replaceAll('-0.0', '-0');
          const second = inner(await callText(lexical));
          assert.ok(Object.is(second.results.torque.power_kw, -0));
          assert.ok(Object.is(second.lineage.torque.exact_value, -0));
          assert.ok(Object.is(JSON.parse(encodeSignedZeroJson(second)).results.statics.plane_1.loads[0].position_mm, -0));
          emit('P1C_ZERO_ROUND_TRIP', { tokens: ['-0.0','-0'], powerNegativeZero: true, lineageNegativeZero: true, positionNegativeZero: true });
        }
        if (mode === 'output-zero') {
          const station = value.lineage.critical_stations.find(s => s.position_mm === .5);
          const displayed = JSON.parse(result.content[0].text).lineage.critical_stations.find(s => s.position_mm === .5);
          assert.ok(Object.is(station.plane_1_moment_nmm, -0));
          assert.ok(Object.is(displayed.plane_1_moment_nmm, -0));
          emit('P1C_COMPUTED_ZERO_ROUND_TRIP', { inputHasNegativeZero: envelope(args).includes('-0.0'),
            valueNegativeZero: Object.is(station.plane_1_moment_nmm,-0), displayedNegativeZero: Object.is(displayed.plane_1_moment_nmm,-0) });
          assert.equal(envelope(args).includes('-0.0'), false);
        }
        if (mode === 'ordered') {
          const second = inner(await call({ ...args, plane_1_loads: [...args.plane_1_loads].reverse(), plane_2_loads: [...args.plane_2_loads].reverse() }));
          assert.equal(encodeSignedZeroJson(value), encodeSignedZeroJson(second));
        }
        if (mode === 'binary64') {
          const bare = envelope(args).replace('1000000000000000100.0','1000000000000000128');
          const second = inner(await callText(bare));
          assert.ok(Object.is(value.results.combined.allowable_shear_mpa, args.allowable_shear_mpa));
          assert.ok(Object.is(second.results.combined.allowable_shear_mpa, args.allowable_shear_mpa));
        }
        if (mode === 'boundary128') assert.equal(value.results.statics.plane_1.loads.length + value.results.statics.plane_2.loads.length, 128);
        emit('P1C_ENGINEERING', { mode, torque_nm: value.results.torque.torque_nm,
          bending_moment_nm: value.results.statics.critical_resultant_bending_moment_nm,
          min_diameter_mm: value.results.combined.min_diameter_mm, reviews: value.reviews,
          models: Object.keys(value.provenance), lineage: value.lineage,
          units: value.results.statics.units });
      } else if (mode === 'invalid-strings') {
        const valid = envelope();
        const invalid = [
          '', '{', valid + '{}', valid + ' null',
          valid.replace('"power_kw":5.5','"power_kw":-1,"power_kw":5.5'),
          valid.replace('"power_kw":5.5','"power_kw":5.5,"po\\u0077er_kw":5.5'),
          valid.replace('"contract_version":"1"','"contract_version":"0","contract_version":"1"'),
          valid.replace('"load_n":500.0','"load_n":1,"load_n":500'),
          ...['NaN','Infinity','1e309','+0','01','0x10','1.','true','"5.5"'].map(n => valid.replace('"power_kw":5.5','"power_kw":'+n)),
          valid.replace('"operation":"' + OPERATION + '"','"operation":"forged"'),
          valid.replace('"input":{','"input":{"__proto__":{},'),
          '{"a":'.repeat(3000) + '0' + '}'.repeat(3000),
          '界'.repeat(6000),
          valid + ' '.repeat(16385 - Buffer.byteLength(valid))
        ];
        for (const text of invalid) failure(await callText(text), 'INVALID_TOOL_INPUT');
        assert.equal(jobs.length, 0); assert.equal(children.length, 0);
        const padded = valid + ' '.repeat(16384 - Buffer.byteLength(valid));
        assert.equal(Buffer.byteLength(padded), 16384);
        assert.equal(inner(await callText(padded)).ok, true);
        emit('P1C_STRING_REJECTIONS', { count: invalid.length, noRejectedStarts: true, exact16384Accepted: true, bytes16385Rejected: true });
      } else if (mode === 'invalid') {
        for (const args of [
          { ...input, support_span_mm: 0 },
          { ...input, plane_1_loads: Array(129).fill({ load_n: 1, position_mm: 0 }) },
          { ...input, plane_1_loads: Array(64).fill({ load_n: 1, position_mm: 0 }), plane_2_loads: Array(65).fill({ load_n: 2, position_mm: 0 }) }
        ]) failure(await call(args), 'INVALID_TOOL_INPUT');
        for (const args of [{ ...input, torque_nm: 999 }, { ...input, assume_constant_torque_over_shaft: false },
          { ...input, plane_1_loads: [{ load_n: 1, position_mm: 0, forged: 1 }] }]) {
          failure(await call(args), 'INVALID_TOOL_INPUT');
        }
        for (const args of [{request_json: 1}, {}, {request_json: envelope(), forged: true}]) {
          const result = await dispatch(args); assert.equal(result.isError, true); assert.equal(result.value, undefined);
        }
        assert.equal(jobs.length, 0); assert.equal(children.length, 0);
      } else if (mode === 'busy') {
        const results = await Promise.all([call(), call()]);
        assert.equal(results.filter(r => !r.isError && inner(r).ok).length, 1);
        failure(results.find(r => !r.isError && !inner(r).ok), 'RESOURCE_BUSY');
      } else if (mode === 'cancel') {
        controller = new AbortController();
        const result = await call(input, controller);
        assert.equal(stopScheduled, true);
        assert.equal(result.isError, true); assert.equal(result.error.info.code, 'ABORTED');
        assert.equal(result.value, undefined); assert.equal(api.overhungSupervisorState(), 'IDLE');
        emit('P1C_HOST_CANCELLATION', { dshCode: result.error.info.code });
      } else if (mode === 'reap-blocked') {
        const release = n.releaseSlot; let fail = true;
        n.releaseSlot = (...args) => { if (fail) { fail = false; throw Error('injected release failure'); } return release(...args); };
        failure(await call(), 'REAP_FAILED'); assert.equal(api.overhungSupervisorState(), 'BLOCKED');
        const starts = children.length; failure(await call(), 'REAP_FAILED'); assert.equal(children.length, starts);
        assert.equal(api.recoverOverhungSupervisor(), true); assert.equal(api.overhungSupervisorState(), 'IDLE');
      } else {
        const codes = { 'parse-timeout': 'TIMEOUT', 'serialize-timeout': 'TIMEOUT', 'compute-timeout': 'TIMEOUT', 'serialize-zero': 'OUTPUT_INVALID', 'serialize-fields': 'OUTPUT_INVALID', timeout: 'TIMEOUT', provenance: 'OUTPUT_INVALID', output: 'OUTPUT_INVALID',
          swap: 'OUTPUT_INVALID', 'review-fail': 'REVIEW_FAIL', 'review-binding': 'REVIEW_FAIL', 'provenance-fail': 'PROVENANCE_ERROR' };
        assert.ok(codes[mode], 'unknown mode'); failure(await call(mode === 'serialize-zero' ? {...input,power_kw:-0} : input), codes[mode]);
        emit('P1C_PUBLIC_FAILURE', { mode, code: codes[mode] });
      }
      assert.equal(observed, callId, 'real registry result events');
      assert.equal(api.overhungSupervisorState(), 'IDLE');
      if (jobs.length) assert.ok(children.every(c => c.launcher && c.member));
      if (['normal','signed-zero','output-zero','boundary128','ordered','binary64'].includes(mode)) assert.deepEqual(grants, Array.from({length: callId}, () => ['resolve','probe','compute']).flat());
      emit('P1C_SUPERVISOR', { mode, grants, jobs, children, observed, state: api.overhungSupervisorState() });
      emit('P1C_DONE', { mode });
    } catch (error) {
      emit('P1C_FAILED', { message: error.message, stack: error.stack });
    }
  });
}
