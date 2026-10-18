#!/usr/bin/env node
// Real DSH rc.2 acceptance preparation. Console evidence only; never a PASS verdict.
import { spawnSync, spawn } from 'node:child_process';
import { resolve, join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
if (args.some(a => !['--config-only','--launch'].includes(a)) || args.length > 1) throw Error('Usage: node scripts/verify_p1c_runtime.mjs [--config-only|--launch]');
const scenarios = args.length ? ['config'] : ['config','reject-config','dsh-inventory11','dsh-inventory12',
  'dsh-legacy11','dsh-normal','dsh-signed-zero','dsh-boundary128','dsh-invalid','dsh-output',
  'dsh-provenance','dsh-swap','dsh-review-fail','dsh-review-binding','dsh-provenance-fail',
  'dsh-busy','dsh-cancel','dsh-timeout','dsh-reap-blocked',"dsh-output-zero","dsh-ordered","dsh-binary64","dsh-invalid-strings","dsh-parse-timeout","dsh-serialize-timeout","dsh-serialize-zero","dsh-serialize-fields","dsh-compute-timeout"];
let failures = 0;
for (const scenario of scenarios) {
  const result = spawnSync(process.execPath, [join(root, 'packages/dsh-mechanical-plugin/test/fixtures/p1c/guard.mjs'), scenario], {
    cwd: root, encoding: 'utf8', timeout: 30000, maxBuffer: 524288, windowsHide: true,
    env: { ...process.env, MECHANICAL_AGENT_TEST_PYTHON:
      process.env.MECHANICAL_AGENT_TEST_PYTHON || process.env.MECHANICAL_AGENT_PYTHON || 'python' }
  });
  process.stdout.write(result.stdout || '');
  if (result.stderr) process.stderr.write(result.stderr);
  const ok = !result.error && result.status === 0 && /EXTERNAL_JOB_EMPTY/.test(result.stdout || '');
  console.log('P1C_CHECK', scenario, ok ? 'OK' : 'FAILED');
  if (!ok) { failures++; if (result.error) console.error(result.error.message); }
}
console.log('P1C_CANDIDATE_CHECKS', JSON.stringify({ total: scenarios.length, failed: failures,
  independentReviewRequired: true }));
process.exitCode = failures ? 1 : 0;
if (args[0] === '--launch' && !failures) {
  const { createInterface } = await import('node:readline');
  const reader = createInterface({ input: process.stdin, output: process.stdout });
  const task = await new Promise(resolveTask => {
    reader.once('line', resolveTask);
    reader.once('close', () => resolveTask(''));
    process.stdout.write('Engineering task (empty input cancels): ');
  });
  reader.close();
  if (!task.trim()) console.log('No task supplied; DSH launch cancelled.');
  else {
    // User text is a separate argv value. No shell, interpolation or command code.
    const child = spawn(process.execPath, [
      join(root,'packages/dsh-mechanical-plugin/node_modules/@deepseek-ai/dsh/lib/bin.js'),
      '--profile','headless','--patch',join(root,'.dsh/mechanical-overhung.patch.yml'),'--','--',task
    ], { cwd: root, env: process.env, stdio: 'inherit', shell: false, windowsHide: true });
    process.exitCode = await new Promise(resolveExit => {
      child.once('error', () => { console.error('Unable to start the explicit DSH profile.'); resolveExit(1); });
      child.once('exit', code => resolveExit(code ?? 1));
    });
  }
}
