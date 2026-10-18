// Approved P1C-B outer carrier. The inner numeric envelope is strictly P1A.
import { OPERATION } from './overhung-input.js';
// rc.2 supports no maxLength keyword. The Supervisor checks the ORIGINAL inner
// UTF-8 text <=16,384 bytes before scanning/parsing, under its single deadline.
export const parameters: any = {
  request_json: { type: 'string', required: true,
    description: 'Complete JSON text of the P1A numeric envelope: {"contract_version":"1","operation":"' + OPERATION +
      '","input":{"power_kw":number,"speed_rpm":number,"support_span_mm":number,"left_overhang_mm":number,"right_overhang_mm":number,' +
      '"plane_1_loads":[{"load_n":number,"position_mm":number}],"plane_2_loads":[{"load_n":number,"position_mm":number}],' +
      '"allowable_shear_mpa":number,"assume_constant_torque_over_shaft":true}}. Supply raw inputs only; at most 128 raw records total and 16,384 UTF-8 bytes. Preserve negative zero as numeric -0 or -0.0. No duplicate keys, intermediate results, paths, commands or source overrides.' }
};
export const envelopeSchema: any = { type: 'object', additionalProperties: false, properties: {
  response_json: { type: 'string', required: true,
    description: 'Validated P1A numeric response JSON text, retaining binary64 and signed-zero. Inspect its inner ok/error: a carrier is not engineering success.' }
} };
