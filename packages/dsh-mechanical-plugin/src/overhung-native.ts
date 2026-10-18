// Explicit 12 Tool profile only. The legacy index never imports this module.
import z from '@deepseek-ai/schemastery';
import { defineTool } from '@deepseek-ai/dsh-tools';
import { OPERATION } from './contracts/overhung-input.js';
import { parameters, envelopeSchema } from './contracts/overhung-native-schema.js';
import { executeOverhungNative } from './supervisor/overhung-supervisor.js';
export const name = 'dsh-mechanical-overhung-native';
export const inject = ['tools'];
export const Config = z.object({
  repositoryRoot: z.string().required(),
  pythonExecutable: z.string(),
  enableVerifiedOverhung: z.boolean().required()
});
export function apply(ctx: any, config: any) {
  if (config.enableVerifiedOverhung !== true) throw Error('Explicit verified overhung opt-in is required.');
  // Registry supplies a fresh frozen arguments snapshot per dispatch. Bind the
  // renderer to this call's already validated, round-trip-checked exact string.
  // Weak keys retain no completed call. No engineering validation is moved
  // beyond the execution deadline and policy replacements cannot forge content.
  const approved = new WeakMap<object, string>();
  const tool = defineTool({
    name: OPERATION,
    description: 'Verified overhung two-plane shaft screening. Pass the P1A raw numeric JSON envelope in request_json; response_json contains the validated P1A result or safe failure. Requires explicit constant-torque acceptance. Reviewed elastic steady-load Tresca minimum diameter only, with Registry provenance and exact Verified Handoff; no fatigue, stress concentration, deflection or production sizing.',
    parameters,
    output: { schema: envelopeSchema, render: (args: any, value: any) => {
      if (typeof value.response_json !== 'string' || approved.get(args) !== value.response_json)
        throw Error('Unbound engineering transport response.');
      return [{ type: 'text', text: value.response_json }];
    } },
    timeoutMs: 18000, // Supervisor: 15s total execution plus its sole <=3s recovery.
    execute: async (args: any, exec: any) => {
      const result = await executeOverhungNative(config, args, exec.signal);
      approved.set(args, result.response_json);
      return result;
    }
  });
  tool.parameters.additionalProperties = false;
  ctx.tools.register(tool);
}
