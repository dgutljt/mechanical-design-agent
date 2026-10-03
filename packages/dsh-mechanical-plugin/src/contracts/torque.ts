export const OPERATION = 'transmitted_torque_v1';
export const CONTRACT_VERSION = '1';
export const successSchema = {
  type: 'object', additionalProperties: false, properties: {
    contract_version: { type: 'string', const: CONTRACT_VERSION, required: true },
    ok: { type: 'boolean', const: true, required: true },
    operation: { type: 'string', const: OPERATION, required: true },
    model_id: { type: 'string', const: OPERATION, required: true },
    calculator_result: { type: 'object', additionalProperties: false, required: true, properties: {
      model_id: { type: 'string', required: true },
      power_kw: { type: 'number', required: true },
      speed_rpm: { type: 'number', required: true },
      torque_nm: { type: 'number', required: true },
      formula: { type: 'string', required: true },
      constant: { type: 'number', required: true }
    } },
    review: { type: 'object', additionalProperties: true, required: true, properties: {
      status: { type: 'string', const: 'PASS', required: true },
      reviewer_version: { type: 'string', required: true },
      checks: { type: 'array', required: true, items: { type: 'object', additionalProperties: true } }
    } },
    provenance: { type: 'object', additionalProperties: false, required: true, properties: {
      model: { type: 'object', additionalProperties: true, required: true },
      sources: { type: 'array', required: true, items: { type: 'object', additionalProperties: true } }
    } },
    warnings: { type: 'array', required: true, items: { type: 'string' } },
    metadata: { type: 'object', additionalProperties: false, required: true, properties: {
      python_project_version: { type: 'string', required: true }
    } }
  }
};
export const failureSchema = {
  type: 'object', additionalProperties: false, properties: {
    contract_version: { type: 'string', const: CONTRACT_VERSION, required: true },
    ok: { type: 'boolean', const: false, required: true },
    operation: { type: 'string', const: OPERATION, required: true },
    error: { type: 'object', additionalProperties: false, required: true, properties: {
      code: { type: 'string', required: true, enum: [
        'INVALID_TOOL_INPUT', 'PYTHON_RESOLUTION_ERROR', 'PYTHON_PROCESS_ERROR',
        'ENGINEERING_INPUT_ERROR', 'CALCULATOR_ERROR', 'REVIEW_FAIL',
        'PROVENANCE_ERROR', 'INTERNAL_ADAPTER_ERROR', 'TIMEOUT', 'CANCELLED'
      ] },
      message: { type: 'string', required: true },
      details: { type: 'object', additionalProperties: true, required: true }
    } },
    metadata: { type: 'object', additionalProperties: true, required: true }
  }
};
export const envelopeSchema = { oneOf: [successSchema, failureSchema] };
export function failure(code: string, message: string) {
  return { contract_version: CONTRACT_VERSION, ok: false, operation: OPERATION,
    error: { code, message, details: {} }, metadata: {} };
}
