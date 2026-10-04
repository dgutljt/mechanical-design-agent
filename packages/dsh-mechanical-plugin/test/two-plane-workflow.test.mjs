import assert from 'node:assert/strict';
import { test } from 'node:test';
import { join, resolve } from 'node:path';
import { apply } from '../dist/index.js';
import { callTwoPlaneWorkflow } from '../dist/bridge/python.js';

const root = resolve(import.meta.dirname, '../../../');
const config = { repositoryRoot: root, pythonExecutable: 'C:/mock/python.exe' };
const input = { power_kw: 5.5, speed_rpm: 960, span_mm: 600,
  plane_1_loads: [{ load_n: -1000, position_mm: 200 }],
  plane_2_loads: [{ load_n: -1000, position_mm: 400 }], allowable_shear_mpa: 40 };
const probe = JSON.stringify({ contract_version: '1', ok: true, python_version: [3, 12, 0],
  python_project_version: '0.1.0', module_source: join(root, 'src/mechanical_agent/bridge/torque_adapter.py'),
  registry_reachable: true });

test('two-plane Native Tool exposes raw inputs only', () => {
  const registered = [];
  apply({ tools: { register: tool => registered.push(tool) } }, config);
  const tool = registered.find(item => item.name === 'analyze_verified_two_plane_shaft_strength');
  assert.ok(tool);
  assert.deepEqual(Object.keys(tool.parameters.properties).sort(), Object.keys(input).sort());
  assert.equal(tool.parameters.properties.plane_1_loads.items.additionalProperties, false);
  assert.equal(tool.parameters.properties.plane_2_loads.items.additionalProperties, false);
});

test('two-plane bridge rejects forged torque, bending, and diameter before spawn', async () => {
  for (const [field, value] of [['torque_nm', 999], ['bending_moment_nm', 1], ['min_diameter_mm', 2]]) {
    const ctx = { subprocess: { spawn() { throw Error('must not spawn'); } } };
    const result = await callTwoPlaneWorkflow(ctx, config, { ...input, [field]: value }, new AbortController().signal);
    assert.equal(result.error.code, 'INVALID_TOOL_INPUT');
  }
  const ctx = { subprocess: { spawn() { throw Error('must not spawn'); } } };
  const poisoned = { ...input, plane_2_loads: [{ ...input.plane_2_loads[0], min_diameter_mm: 2 }] };
  assert.equal((await callTwoPlaneWorkflow(ctx, config, poisoned, new AbortController().signal)).error.code,
    'INVALID_TOOL_INPUT');
});

test('two-plane bridge calls only fixed Python adapter with original input', async () => {
  const calls = [];
  const failed = JSON.stringify({ contract_version: '1', ok: false,
    operation: 'verified_two_plane_shaft_strength_v1',
    error: { code: 'REVIEW_FAIL', message: 'rejected', details: {} }, metadata: {} });
  const ctx = { subprocess: {
    async resolveExecutable(candidate) { return candidate; },
    spawn(spec) {
      calls.push(spec);
      const response = spec.argv.includes('--probe') ? probe : failed;
      return { done: Promise.resolve({ exitCode: 0 }),
        collected: { stdout: { readFrom: () => ({ text: response, lossy: false }) },
          stderr: { readFrom: () => ({ text: '', lossy: false }) } },
        terminate() {}, async waitForExit() { return true; } };
    }
  } };
  const value = await callTwoPlaneWorkflow(ctx, config, input, new AbortController().signal);
  assert.equal(value.error.code, 'REVIEW_FAIL');
  assert.equal('results' in value, false);
  assert.deepEqual(calls[1].argv, ['C:/mock/python.exe', '-m',
    'mechanical_agent.bridge.two_plane_workflow_adapter']);
  assert.deepEqual(JSON.parse(calls[1].stdio.stdin.data).input, input);
});
