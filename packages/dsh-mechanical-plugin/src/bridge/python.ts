import { readFile, realpath } from 'node:fs/promises';
import { isAbsolute, join, resolve, sep } from 'node:path';
import { failure, CONTRACT_VERSION, OPERATION } from '../contracts/torque.js';
import { failure as workflowFailure, OPERATION as WORKFLOW_OPERATION, envelopeSchema as workflowSchema } from '../contracts/shaft-workflow.js';
import { validateJsonSchemaValue, valueSchemaSpecToJsonSchema } from '@deepseek-ai/dsh-tools';

const MODULE = 'mechanical_agent.bridge.torque_adapter';
const WORKFLOW_MODULE = 'mechanical_agent.bridge.shaft_workflow_adapter';
const INPUT_LIMIT = 16_384;
const OUTPUT_LIMIT = 1_048_576;
const STDERR_LIMIT = 16_384;

export async function run(ctx: any, python: string, root: string, args: string[], input: string | undefined,
                   signal: AbortSignal, timeoutMs: number, moduleName = MODULE) {
  if (signal.aborted) return { error: 'CANCELLED' };
  const deadline = new AbortController();
  const onCancel = () => deadline.abort();
  signal.addEventListener('abort', onCancel, { once: true });
  const timer = setTimeout(() => deadline.abort(), timeoutMs);
  let handle;
  try {
    handle = ctx.subprocess.spawn({
      argv: [python, '-m', moduleName, ...args], cwd: root,
      stdio: { stdin: input === undefined ? 'ignore' : { data: input },
        stdout: { maxBytes: OUTPUT_LIMIT }, stderr: { maxBytes: STDERR_LIMIT } },
      graceMs: 2000, signal: deadline.signal,
      env: { PYTHONPATH: join(root, 'src') }
    });
    const outcome = await handle.done;
    const gone = await handle.waitForExit(AbortSignal.timeout(3000));
    if (!gone) return { error: 'PYTHON_PROCESS_ERROR' };
    const stdout = handle.collected.stdout.readFrom(0);
    const stderr = handle.collected.stderr.readFrom(0);
    if (signal.aborted) return { error: 'CANCELLED' };
    if (deadline.signal.aborted) return { error: 'TIMEOUT' };
    if (stdout.lossy || stderr.lossy) return { error: 'PYTHON_PROCESS_ERROR' };
    if (outcome.exitCode !== 0) return { error: 'PYTHON_PROCESS_ERROR' };
    return { stdout: stdout.text };
  } catch {
    return { error: signal.aborted ? 'CANCELLED' : deadline.signal.aborted ? 'TIMEOUT' : 'PYTHON_PROCESS_ERROR' };
  } finally {
    clearTimeout(timer);
    signal.removeEventListener('abort', onCancel);
    if (handle) { handle.terminate(); await handle.waitForExit(AbortSignal.timeout(3000)).catch(() => false); }
  }
}

function parseObject(text: string): any {
  const value = JSON.parse(text);
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Not an object');
  return value;
}

async function probe(ctx: any, candidate: string, root: string, signal: AbortSignal) {
  const executable = await ctx.subprocess.resolveExecutable(candidate, undefined, signal);
  const result = await run(ctx, executable, root, ['--probe'], undefined, signal, 5000);
  if (result.error) throw new Error(result.error);
  const facts = parseObject(result.stdout);
  const source = resolve(facts.module_source || '');
  const intended = join(root, 'src') + sep;
  if (facts.contract_version !== CONTRACT_VERSION || facts.ok !== true ||
      !Array.isArray(facts.python_version) || facts.python_version[0] < 3 ||
      (facts.python_version[0] === 3 && facts.python_version[1] < 12) ||
      facts.python_project_version !== '0.1.0' || facts.registry_reachable !== true ||
      !source.toLowerCase().startsWith(intended.toLowerCase())) throw new Error('Python probe mismatch');
  return executable;
}

export async function resolvePython(ctx: any, config: any, root: string, signal: AbortSignal) {
  const explicit = config.pythonExecutable;
  if (explicit !== undefined) {
    if (!isAbsolute(explicit)) throw new Error('Explicit Python executable must be absolute');
    return probe(ctx, explicit, root, signal);
  }
  if (process.env.MECHANICAL_AGENT_PYTHON) {
    if (!isAbsolute(process.env.MECHANICAL_AGENT_PYTHON)) throw new Error('MECHANICAL_AGENT_PYTHON must be absolute');
    return probe(ctx, process.env.MECHANICAL_AGENT_PYTHON, root, signal);
  }
  const candidates = [process.env.VIRTUAL_ENV && join(process.env.VIRTUAL_ENV, 'Scripts', 'python.exe'),
    process.env.CONDA_PREFIX && join(process.env.CONDA_PREFIX, 'python.exe')].filter(Boolean);
  for (const candidate of candidates) {
    try { return await probe(ctx, candidate, root, signal); } catch { /* try next auto candidate */ }
  }
  try {
    const local = JSON.parse(await readFile(join(root, '.dsh', 'mechanical-plugin.local.json'), 'utf8'));
    if (!local || Object.keys(local).length !== 1 || !isAbsolute(local.pythonExecutable)) {
      throw new Error('Invalid repository Python configuration');
    }
    return probe(ctx, local.pythonExecutable, root, signal);
  } catch (error: any) {
    if (error.code !== 'ENOENT') throw error;
  }
  return probe(ctx, 'python', root, signal);
}

export async function callTorque(ctx: any, config: any, input: any, signal: AbortSignal) {
  let root;
  try {
    if (!isAbsolute(config.repositoryRoot)) throw new Error('Repository root must be absolute');
    root = await realpath(config.repositoryRoot);
  } catch { return failure('PYTHON_RESOLUTION_ERROR', 'Invalid trusted repository root'); }
  let python;
  try { python = await resolvePython(ctx, config, root, signal); }
  catch { return failure(signal.aborted ? 'CANCELLED' : 'PYTHON_RESOLUTION_ERROR', 'Compatible Python interpreter unavailable'); }
  const payload = JSON.stringify({ contract_version: CONTRACT_VERSION, operation: OPERATION, input });
  if (Buffer.byteLength(payload, 'utf8') > INPUT_LIMIT) return failure('INVALID_TOOL_INPUT', 'Input exceeds byte limit');
  const result = await run(ctx, python, root, [], payload, signal, 10000);
  if (result.error) return failure(result.error, result.error === 'TIMEOUT' ? 'Python operation timed out' :
    result.error === 'CANCELLED' ? 'Operation cancelled' : 'Python process failed');
  try {
    const envelope = parseObject(result.stdout);
    if (envelope.contract_version !== CONTRACT_VERSION || envelope.operation !== OPERATION ||
        typeof envelope.ok !== 'boolean') throw new Error('Bad envelope');
    return envelope;
  } catch { return failure('INTERNAL_ADAPTER_ERROR', 'Python adapter returned invalid JSON'); }
}

const WORKFLOW_FIELDS = ['power_kw', 'speed_rpm', 'span_mm', 'loads', 'allowable_shear_mpa'];
function validWorkflowInput(input: any): boolean {
  return !!input && typeof input === 'object' && !Array.isArray(input) &&
    Object.keys(input).length === WORKFLOW_FIELDS.length &&
    WORKFLOW_FIELDS.every(key => Object.hasOwn(input, key)) &&
    WORKFLOW_FIELDS.filter(key => key !== 'loads').every(key =>
      typeof input[key] === 'number' && Number.isFinite(input[key])) &&
    Array.isArray(input.loads) && input.loads.length > 0 &&
    input.loads.every((load: any) => !!load && typeof load === 'object' && !Array.isArray(load) &&
      Object.keys(load).length === 2 && Object.hasOwn(load, 'load_n') &&
      Object.hasOwn(load, 'position_mm') && typeof load.load_n === 'number' &&
      Number.isFinite(load.load_n) && typeof load.position_mm === 'number' &&
      Number.isFinite(load.position_mm));
}

export async function callWorkflow(ctx: any, config: any, input: any, signal: AbortSignal) {
  if (!validWorkflowInput(input)) return workflowFailure('INVALID_TOOL_INPUT', 'Expected raw shaft inputs only');
  let root;
  try {
    if (!isAbsolute(config.repositoryRoot)) throw new Error('Repository root must be absolute');
    root = await realpath(config.repositoryRoot);
  } catch { return workflowFailure('PYTHON_RESOLUTION_ERROR', 'Invalid trusted repository root'); }
  let python;
  try { python = await resolvePython(ctx, config, root, signal); }
  catch { return workflowFailure(signal.aborted ? 'CANCELLED' : 'PYTHON_RESOLUTION_ERROR', 'Compatible Python interpreter unavailable'); }
  const payload = JSON.stringify({ contract_version: CONTRACT_VERSION, operation: WORKFLOW_OPERATION, input });
  if (Buffer.byteLength(payload, 'utf8') > INPUT_LIMIT) return workflowFailure('INVALID_TOOL_INPUT', 'Input exceeds byte limit');
  const result = await run(ctx, python, root, [], payload, signal, 10000, WORKFLOW_MODULE);
  if (result.error) return workflowFailure(result.error, result.error === 'TIMEOUT' ? 'Python operation timed out' :
    result.error === 'CANCELLED' ? 'Operation cancelled' : 'Python process failed');
  try {
    const envelope = parseObject(result.stdout);
    if (validateJsonSchemaValue(valueSchemaSpecToJsonSchema(workflowSchema), envelope).length) throw Error('Bad envelope');
    return envelope;
  } catch { return workflowFailure('INTERNAL_ADAPTER_ERROR', 'Python adapter returned invalid JSON'); }
}
