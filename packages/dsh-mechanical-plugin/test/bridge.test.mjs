import assert from 'node:assert/strict';
import { test } from 'node:test';
import { resolve, join } from 'node:path';
import { callTorque, run, resolvePython } from '../dist/bridge/python.js';
import { envelopeSchema } from '../dist/contracts/torque.js';
import { validateJsonSchemaValue, valueSchemaSpecToJsonSchema } from '@deepseek-ai/dsh-tools';

const root = resolve(import.meta.dirname, '../../../');
const config = { repositoryRoot: root, pythonExecutable: 'C:/mock/python.exe' };
const input = { power_kw: 5.5, speed_rpm: 960 };
const probe = JSON.stringify({ contract_version: '1', ok: true, python_version: [3, 12, 0],
  python_project_version: '0.2.0', module_source: join(root, 'src/mechanical_agent/bridge/torque_adapter.py'),
  registry_reachable: true });
const success = JSON.stringify({ contract_version: '1', ok: true, operation: 'transmitted_torque_v1',
  calculator_result: { torque_nm: 54.713541666666664 } });

function fakeContext(engineering = success, options = {}) {
  const calls = [];
  return { calls, subprocess: {
    async resolveExecutable(candidate) { if (options.resolutionError) throw Error('bad interpreter'); return candidate; },
    spawn(spec) {
      calls.push(spec);
      const isProbe = spec.argv.includes('--probe');
      const text = isProbe ? probe : engineering;
      return {
        done: Promise.resolve({ exitCode: isProbe ? 0 : options.exitCode ?? 0, signal: null }),
        collected: {
          stdout: { readFrom: () => ({ text, lossy: !isProbe && !!options.stdoutLossy }) },
          stderr: { readFrom: () => ({ text: 'diagnostic', lossy: !isProbe && !!options.stderrLossy }) }
        },
        terminate() {}, async waitForExit() { return true; }
      };
    }
  } };
}

test('fixed argv, JSON stdin, and unrounded Python result', async () => {
  const ctx = fakeContext();
  const value = await callTorque(ctx, config, input, new AbortController().signal);
  assert.equal(value.calculator_result.torque_nm, 54.713541666666664);
  assert.deepEqual(ctx.calls[1].argv, ['C:/mock/python.exe', '-m', 'mechanical_agent.bridge.torque_adapter']);
  assert.equal(JSON.parse(ctx.calls[1].stdio.stdin.data).input.power_kw, 5.5);
  assert.equal(ctx.calls[1].cwd, root);
  assert.deepEqual(Object.keys(ctx.calls[1].env), ['PYTHONPATH']);
});

test('explicit wrong interpreter fails closed', async () => {
  const ctx = fakeContext(success, { resolutionError: true });
  const value = await callTorque(ctx, config, input, new AbortController().signal);
  assert.equal(value.error.code, 'PYTHON_RESOLUTION_ERROR');
  assert.equal(ctx.calls.length, 0);
});

test('dedicated Python environment variable is probed before automatic candidates', async () => {
  const previous = process.env.MECHANICAL_AGENT_PYTHON;
  process.env.MECHANICAL_AGENT_PYTHON = 'C:/mock/from-env.exe';
  try {
    const ctx = fakeContext();
    const selected = await resolvePython(ctx, { repositoryRoot: root }, root, new AbortController().signal);
    assert.equal(selected, 'C:/mock/from-env.exe');
    assert.equal(ctx.calls[0].argv[0], selected);
  } finally {
    if (previous === undefined) delete process.env.MECHANICAL_AGENT_PYTHON;
    else process.env.MECHANICAL_AGENT_PYTHON = previous;
  }
});

test('bad dedicated Python environment variable fails closed', async () => {
  const previous = process.env.MECHANICAL_AGENT_PYTHON;
  process.env.MECHANICAL_AGENT_PYTHON = 'C:/mock/bad.exe';
  try {
    await assert.rejects(resolvePython(fakeContext(success, { resolutionError: true }),
      { repositoryRoot: root }, root, new AbortController().signal));
  } finally {
    if (previous === undefined) delete process.env.MECHANICAL_AGENT_PYTHON;
    else process.env.MECHANICAL_AGENT_PYTHON = previous;
  }
});

test('Reviewer failure envelope passes through without a validated result', async () => {
  const reviewFail = JSON.stringify({ contract_version: '1', ok: false, operation: 'transmitted_torque_v1',
    error: { code: 'REVIEW_FAIL', message: 'rejected', details: {} }, metadata: {} });
  const value = await callTorque(fakeContext(reviewFail), config, input, new AbortController().signal);
  assert.equal(value.error.code, 'REVIEW_FAIL');
  assert.equal('calculator_result' in value, false);
});

for (const [name, body, options, code] of [
  ['malformed stdout', '{oops', {}, 'INTERNAL_ADAPTER_ERROR'],
  ['nonzero exit', success, { exitCode: 3 }, 'PYTHON_PROCESS_ERROR'],
  ['stdout limit', success, { stdoutLossy: true }, 'PYTHON_PROCESS_ERROR'],
  ['stderr limit', success, { stderrLossy: true }, 'PYTHON_PROCESS_ERROR']
]) test(name, async () => {
  const value = await callTorque(fakeContext(body, options), config, input, new AbortController().signal);
  assert.equal(value.error.code, code);
  assert.equal('calculator_result' in value, false);
});

test('pre-cancelled signal never spawns a process', async () => {
  const controller = new AbortController(); controller.abort();
  const ctx = fakeContext();
  const result = await run(ctx, config.pythonExecutable, root, [], '{}', controller.signal, 100);
  assert.equal(result.error, 'CANCELLED');
  assert.equal(ctx.calls.length, 0);
});

test('timeout aborts the managed child and joins it', async () => {
  let joined = false;
  const ctx = { subprocess: { spawn(spec) {
    return { done: new Promise(resolve => spec.signal.addEventListener('abort',
      () => resolve({ exitCode: 1, signal: null }), { once: true })),
      collected: { stdout: { readFrom: () => ({ text: '', lossy: false }) },
        stderr: { readFrom: () => ({ text: '', lossy: false }) } },
      terminate() {}, async waitForExit() { joined = true; return true; } };
  } } };
  const result = await run(ctx, config.pythonExecutable, root, [], '{}', new AbortController().signal, 5);
  assert.equal(result.error, 'TIMEOUT');
  assert.equal(joined, true);
});

test('DSH output schema rejects mismatched and contaminated envelopes', () => {
  const schema = valueSchemaSpecToJsonSchema(envelopeSchema);
  const failure = { contract_version: '1', ok: false, operation: 'transmitted_torque_v1',
    error: { code: 'REVIEW_FAIL', message: 'rejected', details: {} }, metadata: {} };
  assert.deepEqual(validateJsonSchemaValue(schema, failure), []);
  assert.notDeepEqual(validateJsonSchemaValue(schema, { ...failure, calculator_result: {} }), []);
  assert.notDeepEqual(validateJsonSchemaValue(schema, { ...failure, error: { ...failure.error, code: 7 } }), []);
});
