// Trusted one-shot runner; only this fixed Adapter can be selected in production.
import { readFile, realpath, access, stat } from 'node:fs/promises';
import { constants } from 'node:fs';
import { isAbsolute, join, resolve } from 'node:path';
import { windowsNative, PROCESS_BYTES, JOB_BYTES } from './windows-native.js';
import { preflightOverhungEnvelope } from '../contracts/overhung-input.js';
import { runnerPhaseControl } from './windows-session.js';
const n = windowsNative();
const protocol = runnerPhaseControl(), send = protocol.send, phase = protocol.phase;
const fail = (code: string): never => { throw Object.assign(Error(code), { code }); };
const sleep = () => new Promise(r => setTimeout(r, 10));
async function run(python: string, root: string, probe: boolean, payload: string) {
  await phase(probe ? 'probe' : 'compute'); protocol.check();
  const child = n.spawn([python, '-s', '-m', probe ? 'mechanical_agent.bridge.torque_adapter' :
    'mechanical_agent.bridge.overhung_two_plane_workflow_adapter', ...(probe ? ['--probe'] : [])], root,
    { ...process.env, PYTHONPATH: join(root, 'src'), PYTHONNOUSERSITE: '1', PYTHONDONTWRITEBYTECODE: '1' } as Record<string, string>);
  let stdout = '', outBytes = 0, errBytes = 0;
  const decoder = new TextDecoder('utf-8', { fatal: true });
  try {
    child.resume(); if (!probe) n.write(child.stdin, payload); child.closeInput();
    while (true) {
      protocol.check();
      const out = n.read(child.stdout), err = n.read(child.stderr);
      outBytes += out.bytes.length; errBytes += err.bytes.length;
      if (outBytes > 1048576 || errBytes > 16384) fail('OUTPUT_TRUNCATED');
      try { stdout += decoder.decode(out.bytes, { stream: true }); } catch { fail('OUTPUT_INVALID'); }
      const exit = n.exitCode(child.process);
      if (exit !== undefined && out.closed && err.closed) {
        protocol.check();
        try { stdout += decoder.decode(); } catch { fail('OUTPUT_INVALID'); }
        if (exit !== 0) fail([0xc0000017, 0xc000012d].includes(exit) ? 'RESOURCE_LIMIT' : 'PYTHON_PROCESS_ERROR');
        return stdout;
      }
      await sleep(); // No provider handle.done participates in supervision.
    }
  } finally { child.close(); }
}
async function resolvePython(config: any, root: string, payload: string) {
  let candidates: string[] = [], strict = false;
  if (config.pythonExecutable !== undefined || process.env.MECHANICAL_AGENT_PYTHON) {
    const explicit = config.pythonExecutable ?? process.env.MECHANICAL_AGENT_PYTHON;
    if (typeof explicit !== 'string' || !isAbsolute(explicit)) fail('PYTHON_RESOLUTION_ERROR');
    candidates = [explicit]; strict = true;
  } else {
    candidates = [process.env.VIRTUAL_ENV && join(process.env.VIRTUAL_ENV, 'Scripts', 'python.exe'),
      process.env.CONDA_PREFIX && join(process.env.CONDA_PREFIX, 'python.exe')].filter(Boolean) as string[];
    try {
      const text = await readFile(join(root, '.dsh', 'mechanical-plugin.local.json'), 'utf8');
      if (Buffer.byteLength(text) > 16384) fail('PYTHON_RESOLUTION_ERROR');
      const local = JSON.parse(text);
      if (Object.keys(local).length !== 1 || typeof local.pythonExecutable !== 'string' || !isAbsolute(local.pythonExecutable)) fail('PYTHON_RESOLUTION_ERROR');
      candidates.push(local.pythonExecutable);
    } catch (e: any) { if (e.code !== 'ENOENT') fail('PYTHON_RESOLUTION_ERROR'); }
    candidates.push(...(process.env.PATH ?? '').split(';').filter(Boolean).map(dir => resolve(dir, 'python.exe')));
  }
  let probeAttempted = false, anyProbeAttempted = false;
  for (const candidate of [...new Set(candidates)]) {
    try {
      const python = await realpath(candidate);
      if (!(await stat(python)).isFile()) continue;
      await access(python, constants.X_OK);
      probeAttempted = true; anyProbeAttempted = true;
      const facts = JSON.parse(await run(python, root, true, payload));
      const source = await realpath(join(root, 'src', 'mechanical_agent', 'bridge', 'torque_adapter.py'));
      if (facts.contract_version !== '1' || facts.ok !== true || facts.python_version?.[0] !== 3 || facts.python_version[1] < 12 ||
          facts.python_project_version !== '0.3.0' || facts.registry_reachable !== true ||
          typeof facts.module_source !== 'string' || (await realpath(facts.module_source)).toLowerCase() !== source.toLowerCase() ||
          typeof facts.repository_root !== 'string' || (await realpath(facts.repository_root)).toLowerCase() !== root.toLowerCase()) fail('PROBE_FAILED');
      return python;
    } catch (e: any) {
      if (['TIMEOUT', 'ISOLATION_UNAVAILABLE', 'REAP_FAILED', 'RESOURCE_LIMIT', 'OUTPUT_TRUNCATED'].includes(e.code)) throw e;
      if (strict) fail(probeAttempted ? 'PROBE_FAILED' : 'PYTHON_RESOLUTION_ERROR');
      if (probeAttempted) { await phase('resolve'); probeAttempted = false; }
    }
  }
  fail(anyProbeAttempted ? 'PROBE_FAILED' : 'PYTHON_RESOLUTION_ERROR');
}
try {
  // Query the actual inherited Job before resolving or starting any interpreter.
  const actual = n.limits(null);
  if (actual.flags !== 0x2308 || actual.processBytes !== PROCESS_BYTES || actual.jobBytes !== JOB_BYTES) fail('ISOLATION_UNAVAILABLE');
  const text = process.env.MECHANICAL_SUPERVISOR_REQUEST;
  delete process.env.MECHANICAL_SUPERVISOR_REQUEST;
  if (typeof text !== 'string' || Buffer.byteLength(text) > 60000) fail('INVALID_TOOL_INPUT');
  const request = JSON.parse(text);
  const prepared = preflightOverhungEnvelope(request.payload);
  await phase('resolve');
  if (typeof request.config.repositoryRoot !== 'string' || !isAbsolute(request.config.repositoryRoot)) fail('PYTHON_RESOLUTION_ERROR');
  const root = await realpath(request.config.repositoryRoot);
  const python = await resolvePython(request.config, root, prepared.payload);
  const payload = await run(python!, root, false, prepared.payload);
  protocol.check(); send({ type: 'output', payload });
} catch (e: any) { send({ type: 'failure', code: typeof e.code === 'string' ? e.code : 'PYTHON_PROCESS_ERROR' }); }
finally { protocol.close(); }
