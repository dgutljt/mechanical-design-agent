// P1C string carrier only. Engineering shapes/numbers remain the P1A contract.
import { guardOverhungEnvelopeBytes, preflightOverhungEnvelope, encodeSignedZeroJson, MAX_INPUT_BYTES } from './overhung-input.js';
import { decodeOverhungResponse, validateOverhungResponse } from './overhung-output.js';

// Linear lexical duplicate-key check. JSON.parse below remains the JSON grammar
// authority. Decoded key equality catches escape aliases, at every object scope.
// Iterative frames avoid an attacker-controlled JS recursion depth.
export function assertUniqueJsonKeys(payload: string) {
  if (typeof payload !== 'string') throw Error('Expected JSON text');
  const frames: { object: boolean, keys: Set<string> }[] = [];
  for (let i = 0; i < payload.length; i++) {
    const c = payload[i];
    if (c === '{' || c === '[') frames.push({ object: c === '{', keys: new Set() });
    else if (c === '}' || c === ']') {
      const frame = frames.pop();
      if (!frame || frame.object !== (c === '}')) throw Error('Invalid JSON containers');
    } else if (c === '"') {
      const start = i;
      let closed = false;
      while (++i < payload.length) {
        if (payload[i] === '\\') i++;
        else if (payload[i] === '"') { closed = true; break; }
      }
      if (!closed) throw Error('Invalid JSON string');
      let next = i + 1;
      while (next < payload.length && /[\x20\t\r\n]/.test(payload[next])) next++;
      if (payload[next] === ':') {
        const frame = frames.at(-1);
        if (!frame?.object) throw Error('Invalid JSON property');
        const key = JSON.parse(payload.slice(start, i + 1));
        if (frame.keys.has(key)) throw Error('Duplicate JSON property');
        frame.keys.add(key);
      }
    }
  }
  if (frames.length) throw Error('Incomplete JSON containers');
}
export function preflightOverhungString(payload: string) {
  if (typeof payload !== 'string' || payload.length > MAX_INPUT_BYTES) throw Error('Input exceeds byte limit');
  guardOverhungEnvelopeBytes(payload); // Original UTF-8 size, BEFORE scanning/parsing.
  assertUniqueJsonKeys(payload);
  return preflightOverhungEnvelope(payload);
}
function sameBinary64(a: any, b: any): boolean {
  if (typeof a !== typeof b) return false;
  if (!a || typeof a !== 'object') return Object.is(a, b);
  if (!b || typeof b !== 'object' || Array.isArray(a) !== Array.isArray(b)) return false;
  const keys = Object.keys(a);
  return keys.length === Object.keys(b).length &&
    keys.every(k => Object.hasOwn(b, k) && sameBinary64(a[k], b[k]));
}
export function serializeOverhungResponse(value: any): string {
  const safe = validateOverhungResponse(value);
  const text = encodeSignedZeroJson(safe);
  assertUniqueJsonKeys(text);
  const decoded = decodeOverhungResponse(text);
  if (!sameBinary64(safe, decoded)) throw Error('Invalid engineering response round trip');
  return text;
}
