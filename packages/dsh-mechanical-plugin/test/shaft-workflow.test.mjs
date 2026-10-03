import assert from 'node:assert/strict';
import { test } from 'node:test';
import { join, resolve } from 'node:path';
import { apply } from '../dist/index.js';
import { callWorkflow, run } from '../dist/bridge/python.js';
import { envelopeSchema } from '../dist/contracts/shaft-workflow.js';
import { validateJsonSchemaValue, valueSchemaSpecToJsonSchema } from '@deepseek-ai/dsh-tools';

const root = resolve(import.meta.dirname, '../../../');
const config = { repositoryRoot: root, pythonExecutable: 'C:/mock/python.exe' };
const input = { power_kw: 5.5, speed_rpm: 960, span_mm: 600,
  loads: [{ load_n: 1000, position_mm: 200 }, { load_n: 500, position_mm: 450 }],
  allowable_shear_mpa: 40 };
const probe = JSON.stringify({ contract_version: '1', ok: true, python_version: [3, 12, 0],
  python_project_version: '0.1.0', module_source: join(root, 'src/mechanical_agent/bridge/torque_adapter.py'),
  registry_reachable: true });
const success = { contract_version: '1', ok: true, operation: 'verified_shaft_strength_v1',
  workflow_id: 'verified_shaft_strength_chain_v1',
  results: { torque: { model_id: 'transmitted_torque_v1', torque_nm: 54.713541666666664 },
    statics: { model_id: 'simply_supported_multi_point_load_v1', reaction_a_n: 791.6666666666667,
      reaction_b_n: 708.3333333333333, max_bending_moment_nm: 158.33333333333334 },
    combined: { model_id: 'solid_shaft_combined_tresca_v1', min_diameter_mm: 27.732717671613003 } },
  reviews: { torque: 'PASS', statics: 'PASS', combined: 'PASS' },
  lineage: { torque: { source_model_id: 'transmitted_torque_v1', source_field: 'torque_nm',
      exact_value: 54.713541666666664 },
    bending_moment: { source_model_id: 'simply_supported_multi_point_load_v1',
      source_field: 'max_bending_moment_nm', exact_value: 158.33333333333334 } },
  provenance: { transmitted_torque_v1: { model: { model_id: 'transmitted_torque_v1' }, sources: [{}] },
    simply_supported_multi_point_load_v1: { model: { model_id: 'simply_supported_multi_point_load_v1' }, sources: [{}] },
    solid_shaft_combined_tresca_v1: { model: { model_id: 'solid_shaft_combined_tresca_v1' }, sources: [{}] } },
  warnings: [], metadata: { python_project_version: '0.1.0' } };

function fakeContext(engineering = JSON.stringify(success), options = {}) {
  const calls = [];
  return { calls, subprocess: {
    async resolveExecutable(candidate) { return candidate; },
    spawn(spec) {
      calls.push(spec);
      const isProbe = spec.argv.includes('--probe');
      return { done: Promise.resolve({ exitCode: isProbe ? 0 : options.exitCode ?? 0 }),
        collected: { stdout: { readFrom: () => ({ text: isProbe ? probe : engineering, lossy: false }) },
          stderr: { readFrom: () => ({ text: '', lossy: false }) } },
        terminate() {}, async waitForExit() { return true; } };
    }
  } };
}

test('model-facing schema has only raw fields and typed nested loads', () => {
  const registered = [];
  apply({ tools: { register: tool => registered.push(tool) } }, config);
  const tool = registered.find(item => item.name === 'analyze_verified_shaft_strength');
  assert.ok(tool);
  assert.deepEqual(Object.keys(tool.parameters.properties).sort(), Object.keys(input).sort());
  assert.equal(tool.parameters.properties.loads.items.additionalProperties, false);
  assert.deepEqual(validateJsonSchemaValue(tool.parameters, input), []);
  assert.notDeepEqual(validateJsonSchemaValue(tool.parameters,
    { ...input, loads: [{ load_n: 1000, position_mm: 200, torque_nm: 999 }] }), []);
  // DSH's root DSL currently leaves additionalProperties unspecified. The bridge must reject it.
  assert.equal(tool.parameters.additionalProperties, undefined);
});

test('bridge accepts only raw inputs before spawning', async () => {
  for (const poisoned of [{ ...input, torque_nm: 999999 },
    { ...input, max_bending_moment_nm: 1 },
    { ...input, loads: [{ load_n: 1000, position_mm: 200, torque_nm: 999 }] }]) {
    const ctx = fakeContext();
    const value = await callWorkflow(ctx, config, poisoned, new AbortController().signal);
    assert.equal(value.error.code, 'INVALID_TOOL_INPUT');
    assert.equal(ctx.calls.length, 0);
  }
});

test('bridge uses fixed workflow module and preserves JSON numbers', async () => {
  const ctx = fakeContext();
  const value = await callWorkflow(ctx, config, input, new AbortController().signal);
  assert.equal(value.ok, true);
  assert.equal(value.results.torque.torque_nm, 54.713541666666664);
  assert.deepEqual(ctx.calls[1].argv, ['C:/mock/python.exe', '-m',
    'mechanical_agent.bridge.shaft_workflow_adapter']);
  assert.deepEqual(JSON.parse(ctx.calls[1].stdio.stdin.data).input, input);
  assert.equal(ctx.calls[1].cwd, root);
});

test('failure envelope and malformed output cannot expose a result', async () => {
  const failed = { contract_version: '1', ok: false, operation: 'verified_shaft_strength_v1',
    error: { code: 'REVIEW_FAIL', message: 'rejected', details: {} }, metadata: {} };
  assert.deepEqual(validateJsonSchemaValue(valueSchemaSpecToJsonSchema(envelopeSchema), failed), []);
  const result = await callWorkflow(fakeContext(JSON.stringify(failed)), config, input,
    new AbortController().signal);
  assert.equal(result.error.code, 'REVIEW_FAIL');
  assert.equal('results' in result, false);
  const bad = await callWorkflow(fakeContext('{broken'), config, input, new AbortController().signal);
  assert.equal(bad.error.code, 'INTERNAL_ADAPTER_ERROR');
  const contaminated = await callWorkflow(fakeContext(JSON.stringify({ ...failed, results: success.results })),
    config, input, new AbortController().signal);
  assert.equal(contaminated.error.code, 'INTERNAL_ADAPTER_ERROR');
  const wrongOutput = await callWorkflow(fakeContext(JSON.stringify({ ...success, reviews: { ...success.reviews,
    combined: 'FAIL' } })), config, input, new AbortController().signal);
  assert.equal(wrongOutput.error.code, 'INTERNAL_ADAPTER_ERROR');
});

test('workflow process cancellation and timeout use managed subprocess', async () => {
  const controller = new AbortController(); controller.abort();
  const ctx = fakeContext();
  assert.equal((await run(ctx, config.pythonExecutable, root, [], '{}', controller.signal, 5,
    'mechanical_agent.bridge.shaft_workflow_adapter')).error, 'CANCELLED');
  assert.equal(ctx.calls.length, 0);
  let joined = false;
  const blocking = { subprocess: { spawn(spec) {
    return { done: new Promise(resolve => spec.signal.addEventListener('abort',
      () => resolve({ exitCode: 1 }), { once: true })),
      collected: { stdout: { readFrom: () => ({ text: '', lossy: false }) },
        stderr: { readFrom: () => ({ text: '', lossy: false }) } },
      terminate() {}, async waitForExit() { joined = true; return true; } };
  } } };
  assert.equal((await run(blocking, config.pythonExecutable, root, [], '{}',
    new AbortController().signal, 5, 'mechanical_agent.bridge.shaft_workflow_adapter')).error, 'TIMEOUT');
  assert.equal(joined, true);
});
