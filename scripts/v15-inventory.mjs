// Read-only runtime probe. This is mounted after the engineering plugin.
export const name = 'v15-inventory';
export const inject = ['tools', 'profileContext'];
export function apply(ctx) {
  ctx.on('tools/result', (exec, result) => {
    if (['calculate_transmitted_torque', 'analyze_verified_shaft_strength', 'analyze_verified_two_plane_shaft_strength'].includes(exec.name)) {
      process.stderr.write('ACCEPTANCE_TOOL_RESULT ' + JSON.stringify({
        callId: exec.callId, tool: exec.name, isError: result.isError, value: result.value
      }) + '\n');
    }
  });
  setImmediate(() => process.stderr.write('ACCEPTANCE_INVENTORY ' + JSON.stringify({
    tools: ctx.tools.schemas().map(schema => schema.name).sort(),
    bundles: ctx.profileContext.startedBundles
  }) + '\n'));
}
