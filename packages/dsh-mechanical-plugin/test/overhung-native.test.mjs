import assert from 'node:assert/strict';
import { test } from 'node:test';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
const guard = fileURLToPath(new URL('./fixtures/p1c/guard.mjs', import.meta.url));
for (const scenario of ["sorting-normal","sorting-boundary","sorting-tamper","transport-parity","config","reject-config","dsh-inventory11","dsh-inventory12","dsh-legacy11","dsh-normal","dsh-signed-zero","dsh-boundary128","dsh-invalid","dsh-output","dsh-provenance","dsh-swap","dsh-review-fail","dsh-review-binding","dsh-provenance-fail","dsh-busy","dsh-cancel","dsh-timeout","dsh-reap-blocked","dsh-output-zero","dsh-ordered","dsh-binary64","dsh-invalid-strings","dsh-parse-timeout","dsh-serialize-timeout","dsh-serialize-zero","dsh-serialize-fields","dsh-compute-timeout"]) {
  test('P1C real supervised path: ' + scenario, { timeout: 35000, skip: process.platform !== 'win32' }, () => {
    const result = spawnSync(process.execPath, [guard, scenario], {
      encoding: 'utf8', timeout: 30000, maxBuffer: 524288, windowsHide: true,
      env: { ...process.env, MECHANICAL_AGENT_TEST_PYTHON:
        process.env.MECHANICAL_AGENT_TEST_PYTHON || process.env.MECHANICAL_AGENT_PYTHON || 'python' }
    });
    assert.equal(result.error, undefined, result.stderr);
    assert.equal(result.status, 0, result.stdout + '\n' + result.stderr);
    assert.match(result.stdout, /EXTERNAL_JOB_EMPTY/); process.stdout.write(result.stdout);
  });
}

// Contract tests use only the approved P1A preflight and new lexical duplicate gate.
import { preflightOverhungString } from '../dist/contracts/overhung-transport.js';
import { preflightOverhungEnvelope, encodeSignedZeroJson, OPERATION } from '../dist/contracts/overhung-input.js';
test('P1C string parser preserves P1A lexical binary64 semantics and rejects key aliases', () => {
  const args = { power_kw: -0, speed_rpm: 960, support_span_mm: 600, left_overhang_mm: 100,
    right_overhang_mm: 0, plane_1_loads: [{load_n:-0,position_mm:-0}], plane_2_loads: [],
    allowable_shear_mpa: 1000000000000000100, assume_constant_torque_over_shaft: true };
  const text = encodeSignedZeroJson({contract_version:'1',operation:OPERATION,input:args});
  for (const payload of [text, text.replaceAll('-0.0','-0'),
    text.replace('1000000000000000100.0','1000000000000000128'), text + ' '.repeat(16384-Buffer.byteLength(text))]) {
    const a=preflightOverhungString(payload), b=preflightOverhungEnvelope(payload);
    assert.equal(a.payload,b.payload);
    assert.ok(Object.is(a.request.input.power_kw,-0));
    assert.ok(Object.is(a.request.input.plane_1_loads[0].load_n,-0));
    assert.ok(Object.is(a.request.input.plane_1_loads[0].position_mm,-0));
    assert.ok(Object.is(a.request.input.allowable_shear_mpa,args.allowable_shear_mpa));
  }
  for (const payload of [
    text.replace('"power_kw":-0.0','"power_kw":1,"power_kw":-0'),
    text.replace('"power_kw":-0.0','"power_kw":-0,"po\\\\u0077er_kw":-0'),
    text.replace('"load_n":-0.0','"load_n":0,"load_n":-0'),
    text+'{}', text+' '.repeat(16385-Buffer.byteLength(text))
  ]) assert.throws(()=>preflightOverhungString(payload));
});
