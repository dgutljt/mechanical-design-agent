import { CONTRACT_VERSION } from './torque.js';

export const OPERATION = 'verified_two_plane_shaft_strength_v1';
const review = { type: 'string', const: 'PASS', required: true };
const torqueResult = { type: 'object', additionalProperties: true, required: true, properties: {
  model_id: { type: 'string', const: 'transmitted_torque_v1', required: true },
  torque_nm: { type: 'number', required: true }
} };
const station = { type: 'object', additionalProperties: false, properties: {
  position_mm: { type: 'number', required: true },
  plane_1_moment_nmm: { type: 'number', required: true },
  plane_2_moment_nmm: { type: 'number', required: true },
  resultant_bending_moment_nmm: { type: 'number', required: true }
} };
const region = { type: 'object', additionalProperties: false, properties: {
  x_start_mm: { type: 'number', required: true }, x_end_mm: { type: 'number', required: true }
} };
const staticsResult = { type: 'object', additionalProperties: true, required: true, properties: {
  model_id: { type: 'string', const: 'simply_supported_two_plane_point_load_v1', required: true },
  critical_resultant_bending_moment_nm: { type: 'number', required: true },
  critical_stations: { type: 'array', required: true, items: station },
  critical_regions: { type: 'array', required: true, items: region }
} };
const combinedResult = { type: 'object', additionalProperties: true, required: true, properties: {
  model_id: { type: 'string', const: 'solid_shaft_combined_tresca_v1', required: true },
  min_diameter_mm: { type: 'number', required: true }
} };
const provenanceRecord = { type: 'object', additionalProperties: false, required: true, properties: {
  model: { type: 'object', additionalProperties: true, required: true, properties: {
    model_id: { type: 'string', required: true }
  } },
  sources: { type: 'array', required: true, items: { type: 'object', additionalProperties: true } }
} };
const lineageRecord = { type: 'object', additionalProperties: false, required: true, properties: {
  source_model_id: { type: 'string', required: true },
  source_field: { type: 'string', required: true },
  exact_value: { type: 'number', required: true }
} };
export const successSchema = { type: 'object', additionalProperties: false, properties: {
  contract_version: { type: 'string', const: CONTRACT_VERSION, required: true },
  ok: { type: 'boolean', const: true, required: true },
  operation: { type: 'string', const: OPERATION, required: true },
  workflow_id: { type: 'string', const: 'verified_two_plane_shaft_strength_chain_v1', required: true },
  results: { type: 'object', additionalProperties: false, required: true, properties: {
    torque: torqueResult, statics: staticsResult, combined: combinedResult
  } },
  reviews: { type: 'object', additionalProperties: false, required: true, properties: {
    torque: review, statics: review, combined: review
  } },
  lineage: { type: 'object', additionalProperties: false, required: true, properties: {
    torque: lineageRecord, bending_moment: lineageRecord,
    critical_stations: { type: 'array', required: true, items: station },
    critical_regions: { type: 'array', required: true, items: region }
  } },
  provenance: { type: 'object', additionalProperties: false, required: true, properties: {
    transmitted_torque_v1: provenanceRecord,
    simply_supported_two_plane_point_load_v1: provenanceRecord,
    solid_shaft_combined_tresca_v1: provenanceRecord
  } },
  warnings: { type: 'array', required: true, items: { type: 'string' } },
  metadata: { type: 'object', additionalProperties: false, required: true, properties: {
    python_project_version: { type: 'string', required: true }
  } }
} };
export const failureSchema = { type: 'object', additionalProperties: false, properties: {
  contract_version: { type: 'string', const: CONTRACT_VERSION, required: true },
  ok: { type: 'boolean', const: false, required: true },
  operation: { type: 'string', const: OPERATION, required: true },
  error: { type: 'object', additionalProperties: false, required: true, properties: {
    code: { type: 'string', required: true, enum: [
      'INVALID_TOOL_INPUT', 'PYTHON_RESOLUTION_ERROR', 'PYTHON_PROCESS_ERROR',
      'ENGINEERING_INPUT_ERROR', 'CALCULATOR_ERROR', 'REVIEW_FAIL',
      'PROVENANCE_ERROR', 'LINEAGE_ERROR', 'INTERNAL_ADAPTER_ERROR', 'TIMEOUT', 'CANCELLED'
    ] },
    message: { type: 'string', required: true },
    details: { type: 'object', additionalProperties: true, required: true }
  } },
  metadata: { type: 'object', additionalProperties: true, required: true }
} };
export const envelopeSchema = { oneOf: [successSchema, failureSchema] };
export function failure(code: string, message: string) {
  return { contract_version: CONTRACT_VERSION, ok: false, operation: OPERATION,
    error: { code, message, details: {} }, metadata: {} };
}
