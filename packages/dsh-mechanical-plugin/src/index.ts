import z from '@deepseek-ai/schemastery';
import { defineTool } from '@deepseek-ai/dsh-tools';
import { callTorque } from './bridge/python.js';
import { envelopeSchema } from './contracts/torque.js';

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
}
