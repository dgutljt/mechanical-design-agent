// Unregistered new-overhung entry. Legacy Bridge and registrations do not import it.
import { preflightOverhungInput } from '../contracts/overhung-input.js';
import { decodeOverhungResponse, validateOverhungResponse } from '../contracts/overhung-output.js';
import { runWindowsSession, sessionTermination, monotonicNow, RUN_MS } from './windows-session.js';
import { windowsNative } from './windows-native.js';
import { types } from 'node:util';
const slotKey = Symbol.for('mechanical-agent.overhung-supervisor.slot.v1');
const host = process as any;
if (!host[slotKey]) Object.defineProperty(host, slotKey, { value: { state: 'IDLE', rescue: undefined, generation: 0 }, writable: false });
const slot = host[slotKey];
const messages: Record<string, string> = {
  RESOURCE_BUSY: 'Engineering execution is busy.', TIMEOUT: 'Engineering operation timed out.', CANCELLED: 'Engineering operation cancelled.',
  ISOLATION_UNAVAILABLE: 'Required process isolation is unavailable.', RESOURCE_LIMIT: 'Engineering resource limit reached.',
  REAP_FAILED: 'Engineering isolation requires recovery.', PYTHON_RESOLUTION_ERROR: 'Compatible interpreter unavailable.',
  PROBE_FAILED: 'Interpreter verification failed.', PYTHON_PROCESS_ERROR: 'Engineering process failed.',
  OUTPUT_INVALID: 'Engineering output is invalid.', OUTPUT_TRUNCATED: 'Engineering output is incomplete.', INVALID_TOOL_INPUT: 'Invalid engineering request.'
};
function failure(code: string) {
  if (!Object.hasOwn(messages, code)) code = 'PYTHON_PROCESS_ERROR';
  return validateOverhungResponse({ contract_version: '1', operation: 'verified_overhung_two_plane_shaft_strength_chain_v1',
    ok: false, error: { code, message: messages[code] }, metadata: {} });
}
function boundToRequest(value: any, request: any) {
  if (!value.ok) return true;
  const input = request.input, results = value.results, statics = results.statics;
  return Object.is(input.power_kw, results.torque.power_kw) && Object.is(input.speed_rpm, results.torque.speed_rpm) &&
    Object.is(input.allowable_shear_mpa, results.combined.allowable_shear_mpa) &&
    ['support_span_mm', 'left_overhang_mm', 'right_overhang_mm'].every(k => Object.is(input[k], statics[k])) &&
    ['plane_1', 'plane_2'].every(plane => {
      const loads = input[plane + '_loads'], actual = statics[plane].loads;
      return loads.length === actual.length && loads.every((load: any, i: number) => Object.is(load.load_n, actual[i].load_n) && Object.is(load.position_mm, actual[i].position_mm));
    });
}
// There is deliberately no backend, runner, limit or module override here.
export async function executeOverhung(config: any, args: any, signal: AbortSignal) {
  const expires = monotonicNow() + RUN_MS;
  const termination = sessionTermination(expires, signal);
  try {
    // Bound the shape BEFORE the generic P1A snapshot. Reject accessors/proxies
    // without invoking user code and reject unexpected subtrees before traversal.
    const fields = ['power_kw', 'speed_rpm', 'support_span_mm', 'left_overhang_mm', 'right_overhang_mm',
      'plane_1_loads', 'plane_2_loads', 'allowable_shear_mpa', 'assume_constant_torque_over_shaft'];
    function data(value: any, keys: string[]) {
      if (!value || typeof value !== 'object' || types.isProxy(value)) throw Error();
      const proto = Object.getPrototypeOf(value);
      if (proto !== Object.prototype && proto !== null) throw Error();
      const own = Reflect.ownKeys(value);
      if (own.length !== keys.length || !keys.every(k => own.includes(k))) throw Error();
      return Object.fromEntries(keys.map(k => {
        const d = Object.getOwnPropertyDescriptor(value, k)!;
        if (!Object.hasOwn(d, 'value') || !d.enumerable) throw Error();
        return [k, d.value];
      }));
    }
    let prepared;
    try {
      const bounded = data(args, fields);
      for (const field of fields) {
        const v = bounded[field];
        if (!field.endsWith('_loads')) { if (typeof v !== (field === 'assume_constant_torque_over_shaft' ? 'boolean' : 'number')) throw Error(); continue; }
        if (types.isProxy(v) || !Array.isArray(v) || Object.getPrototypeOf(v) !== Array.prototype || v.length > 128) throw Error();
        if (Reflect.ownKeys(v).length !== v.length + 1) throw Error();
        bounded[field] = Array.from({ length: v.length }, (_, i) => {
          const d = Object.getOwnPropertyDescriptor(v, String(i));
          if (!d || !Object.hasOwn(d, 'value') || !d.enumerable) throw Error();
          const load = data(d.value, ['load_n', 'position_mm']);
          if (typeof load.load_n !== 'number' || typeof load.position_mm !== 'number') throw Error();
          return load;
        });
      }
      prepared = preflightOverhungInput(bounded);
    } catch { return failure(termination.observe() ?? 'INVALID_TOOL_INPUT'); }
    if (termination.observe()) return failure(termination.observe()!);
    if (slot.state === 'BLOCKED') return failure('REAP_FAILED');
    if (slot.state !== 'IDLE') return failure('RESOURCE_BUSY');
    let native;
    try {
      native = windowsNative();
      slot.semaphore ??= native.openSlot();
      if (!native.acquireSlot(slot.semaphore)) return failure(termination.observe() ?? 'RESOURCE_BUSY');
    } catch { return failure(termination.observe() ?? 'ISOLATION_UNAVAILABLE'); }
    slot.rangeEmpty = false;
    slot.recover = undefined; slot.canRecover = undefined;
    slot.state = 'RUNNING'; const generation = ++slot.generation;
    let result: any, value: any;
    try {
      // Config is host-owned. Interpreter and root resolution occur INSIDE the Job.
      const request = JSON.stringify({ payload: prepared.payload, config: {
        repositoryRoot: config.repositoryRoot, ...(config.pythonExecutable === undefined ? {} : { pythonExecutable: config.pythonExecutable })
      } });
      result = await runWindowsSession({ request, cwd: process.cwd(), expires, termination }, text => {
        const decoded = decodeOverhungResponse(text);
        if (!boundToRequest(decoded, prepared!.request)) return false;
        value = decoded; return true;
      }, signal);
      slot.recover = result.recover;
      slot.canRecover = result.recoveryReady;
      if (!result.empty) { slot.state = 'BLOCKED'; return failure('REAP_FAILED'); }
      if (!result.handlesClosed) { slot.state = 'BLOCKED'; return failure('REAP_FAILED'); }
      slot.rangeEmpty = true;
      // An abnormal launcher exit is reviewable only after explicit recovery,
      // even when the host has already proved both emptiness and handle closure.
      if (result.code === 'REAP_FAILED') { slot.state = 'BLOCKED'; return failure('REAP_FAILED'); }
      // Session failure is already latched; late caller state cannot relabel it.
      if (!result.success) return failure(result.code);
      if (termination.observe()) return failure(termination.observe()!);
      return value;
    } catch {
      slot.state = 'BLOCKED'; return failure('REAP_FAILED');
    } finally {
      if (slot.generation === generation && slot.state !== 'BLOCKED') {
        try { native.releaseSlot(slot.semaphore); slot.state = 'IDLE'; }
        catch { slot.state = 'BLOCKED'; return failure('REAP_FAILED'); }
      }
    }
  } finally { termination.dispose(); }
}
export function overhungSupervisorState() { return slot.state as 'IDLE' | 'RUNNING' | 'BLOCKED'; }
// Explicit host/operator action only. No force-reset and no automatic recovery.
export function recoverOverhungSupervisor() {
  if (slot.state !== 'BLOCKED') return false;
  try {
    if (slot.canRecover && !slot.canRecover()) return false;
    const n = windowsNative();
    if (slot.recover) { if (!slot.recover()) return false; slot.rangeEmpty = true; }
    if (!slot.rangeEmpty) return false;
    n.releaseSlot(slot.semaphore); slot.state = 'IDLE'; return true;
  } catch { return false; }
}
