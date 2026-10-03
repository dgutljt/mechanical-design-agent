import z from '@deepseek-ai/schemastery';
import { defineTool } from '@deepseek-ai/dsh-tools';
import { callTorque, callWorkflow } from './bridge/python.js';
import { envelopeSchema } from './contracts/torque.js';
import { envelopeSchema as workflowEnvelopeSchema } from './contracts/shaft-workflow.js';

export const name = 'dsh-mechanical-plugin';
export const inject = ['tools', 'subprocess'];
export const Config = z.object({
  repositoryRoot: z.string().required(),
  pythonExecutable: z.string()
});

export function apply(ctx: any, config: any) {
  ctx.tools.register(defineTool({
    name: 'calculate_transmitted_torque',
    description: 'Calculate transmitted torque through the Python calculator, mandatory Reviewer, and Registry provenance.',
    parameters: {
      power_kw: { type: 'number', required: true, description: 'Mechanical power in kW' },
      speed_rpm: { type: 'number', required: true, description: 'Rotational speed in rpm' }
    },
    output: {
      schema: envelopeSchema,
      render: (_args: any, value: any) => [{ type: 'text', text: JSON.stringify(value) }]
    },
    timeoutMs: 20000,
    execute: (args: any, exec: any) => callTorque(ctx, config, args, exec.signal)
  }));
  ctx.tools.register(defineTool({
    name: 'analyze_verified_shaft_strength',
    description: 'Analyze a simply supported shaft using existing calculators, mandatory Reviewers, verified handoff, and Registry provenance. Supply only raw engineering inputs.',
    parameters: {
      power_kw: { type: 'number', required: true, description: 'Mechanical power in kW' },
      speed_rpm: { type: 'number', required: true, description: 'Rotational speed in rpm' },
      span_mm: { type: 'number', required: true, description: 'Support span in mm' },
      loads: { type: 'array', required: true, description: 'Same-direction transverse point loads within the span',
        items: { type: 'object', additionalProperties: false, properties: {
          load_n: { type: 'number', required: true, description: 'Load magnitude in N' },
          position_mm: { type: 'number', required: true, description: 'Position from support A in mm' }
        } } },
      allowable_shear_mpa: { type: 'number', required: true, description: 'Allowable shear stress in MPa' }
    },
    output: {
      schema: workflowEnvelopeSchema,
      render: (_args: any, value: any) => [{ type: 'text', text: JSON.stringify(value) }]
    },
    timeoutMs: 20000,
    execute: (args: any, exec: any) => callWorkflow(ctx, config, args, exec.signal)
  }));
}
