// Phase 14C-P1A: independent contract only; no Native Tool is registered here.
import { types } from 'node:util';
import { CONTRACT_VERSION } from './torque.js';

export const OPERATION = 'verified_overhung_two_plane_shaft_strength_chain_v1';
export const MAX_LOAD_RECORDS = 128;
export const MAX_INPUT_BYTES = 16_384;
const FIELDS = ['power_kw', 'speed_rpm', 'support_span_mm', 'left_overhang_mm',
  'right_overhang_mm', 'plane_1_loads', 'plane_2_loads', 'allowable_shear_mpa',
  'assume_constant_torque_over_shaft'];

export class OverhungInputError extends Error {
  readonly code = 'INVALID_TOOL_INPUT';
}
function reject(message: string): never { throw new OverhungInputError(message); }
function number(value: any) {
  if (typeof value !== 'number' || !Number.isFinite(value)) reject('Expected finite JSON numbers');
}

// Node's native isProxy check does not execute Proxy traps, including on revoked
// proxies. It MUST precede every reflection, enumeration or property access on
// caller objects. Only values from ordinary own data descriptors are copied.
// Returned records have null prototypes; all nested data is private and frozen.
export function snapshotJsonData(value: any, maxArrayLength?: number): any {
  const active = new Set();
  function copy(v: any): any {
    if (types.isProxy(v)) reject('Proxy values are not JSON data');
    if (v === null || typeof v === 'string' || typeof v === 'boolean') return v;
    if (typeof v === 'number') { number(v); return v; }
    if (!v || typeof v !== 'object' || active.has(v)) reject('Unsupported or cyclic JSON value');
    const array = Array.isArray(v);
    const prototype = Object.getPrototypeOf(v);
    if (array ? prototype !== Array.prototype : prototype !== Object.prototype && prototype !== null) reject('Expected ordinary JSON data');
    active.add(v);
    let result;
    if (array) {
      const length = Object.getOwnPropertyDescriptor(v, 'length')!.value;
      if (maxArrayLength !== undefined && length > maxArrayLength) reject('Plane exceeds 128 raw load records');
      if (Reflect.ownKeys(v).length !== length + 1) reject('Expected dense JSON array only');
      result = [];
      for (let i = 0; i < length; i++) {
        const d = Object.getOwnPropertyDescriptor(v, String(i));
        if (!d || !Object.hasOwn(d, 'value') || !d.enumerable) reject('Expected own JSON array data');
        result.push(copy(d.value));
      }
    } else {
      const keys = Reflect.ownKeys(v);
      if (keys.some(k => typeof k !== 'string')) reject('Expected string JSON keys');
      result = Object.create(null);
      for (const key of keys as string[]) {
        const d = Object.getOwnPropertyDescriptor(v, key);
        if (!d || !Object.hasOwn(d, 'value') || !d.enumerable) reject('Expected own JSON data properties');
        result[key] = copy(d.value);
      }
    }
    active.delete(v);
    return Object.freeze(result);
  }
  return copy(value);
}

// Below this boundary, every object is a private descriptor snapshot.
function record(value: any, fields: string[]) {
  if (!value || typeof value !== 'object' || Array.isArray(value) ||
      Object.keys(value).length !== fields.length || !fields.every(k => Object.hasOwn(value, k))) reject('Unexpected or missing JSON fields');
}
function validateSnapshot(input: any) {
  record(input, FIELDS);
  for (const key of FIELDS.filter(k => !k.endsWith('_loads') && k !== 'assume_constant_torque_over_shaft')) number(input[key]);
  if (input.assume_constant_torque_over_shaft !== true) reject('Constant torque confirmation must be boolean true');
  for (const plane of [input.plane_1_loads, input.plane_2_loads]) {
    if (!Array.isArray(plane)) reject('Expected load array');
    if (plane.length > MAX_LOAD_RECORDS) reject('Plane exceeds 128 raw load records');
    for (const load of plane) { record(load, ['load_n', 'position_mm']); number(load.load_n); number(load.position_mm); }
  }
  if (input.plane_1_loads.length + input.plane_2_loads.length > MAX_LOAD_RECORDS) reject('Total exceeds 128 raw load records');
  const end = input.support_span_mm + input.right_overhang_mm;
  if (input.power_kw < 0 || input.speed_rpm <= 0 || input.allowable_shear_mpa <= 0 ||
      input.support_span_mm <= 0 || input.left_overhang_mm < 0 || input.right_overhang_mm < 0 ||
      (input.left_overhang_mm === 0 && input.right_overhang_mm === 0) ||
      !Number.isFinite(end) || !Number.isFinite(input.left_overhang_mm + end)) reject('Input outside engineering domain');
  for (const plane of [input.plane_1_loads, input.plane_2_loads]) {
    for (const load of plane) {
      if (load.position_mm < -input.left_overhang_mm || load.position_mm > end) reject('Load outside shaft domain');
    }
  }
}
export function validateOverhungInput(input: any) {
  const snapshot = snapshotJsonData(input, MAX_LOAD_RECORDS);
  validateSnapshot(snapshot);
  return snapshot;
}

// All JS numbers are binary64, even integral values outside the safe-integer
// range. A bare integer token would make Python retain its decimal text as an
// arbitrary-precision int instead. Emit a floating token for EVERY number:
// keep the shortest round-trip decimal, adding .0 if it has no decimal/exponent.
// -0.0 separately retains zero's sign. No tags or protocol changes are needed.
export function encodeSignedZeroJson(value: any): string {
  const snapshot = snapshotJsonData(value);
  function encode(v: any): string {
    if (v === null) return 'null';
    if (typeof v === 'number') {
      if (Object.is(v, -0)) return '-0.0';
      const token = JSON.stringify(v);
      return /[.eE]/.test(token) ? token : token + '.0';
    }
    if (typeof v === 'string' || typeof v === 'boolean') return JSON.stringify(v);
    if (Array.isArray(v)) return '[' + v.map(encode).join(',') + ']';
    return '{' + Object.keys(v).map(k => JSON.stringify(k) + ':' + encode(v[k])).join(',') + '}';
  }
  return encode(snapshot);
}

export function guardOverhungEnvelopeBytes(payload: string): void {
  if (typeof payload !== 'string' || Buffer.byteLength(payload, 'utf8') > MAX_INPUT_BYTES) reject('Complete envelope exceeds 16384 UTF-8 bytes');
}

// Bound ORIGINAL UTF-8 bytes before parsing, then bound the canonical floating-
// token envelope again. Both steps precede interpreter resolution/probe.
export function preflightOverhungEnvelope(payload: string) {
  guardOverhungEnvelopeBytes(payload);
  let parsed;
  try { parsed = JSON.parse(payload); } catch { reject('Invalid JSON envelope'); }
  const request = snapshotJsonData(parsed, MAX_LOAD_RECORDS);
  record(request, ['contract_version', 'operation', 'input']);
  if (request.contract_version !== CONTRACT_VERSION || request.operation !== OPERATION) reject('Unsupported version or operation');
  validateSnapshot(request.input);
  const encoded = encodeSignedZeroJson(request);
  guardOverhungEnvelopeBytes(encoded);
  return Object.freeze({ payload: encoded, request });
}

// Future Native entry: preflight FIRST; send only its frozen snapshot payload.
// Only then resolve the trusted interpreter, probe and start the fixed Adapter.
export function preflightOverhungInput(input: any) {
  const snapshot = validateOverhungInput(input);
  const request = Object.freeze({ contract_version: CONTRACT_VERSION, operation: OPERATION, input: snapshot });
  const payload = encodeSignedZeroJson(request);
  guardOverhungEnvelopeBytes(payload);
  return Object.freeze({ payload, request });
}
