// Independent bounded outer Job for each disposable P1C test host and descendants.
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { windowsNative } from '../../../dist/supervisor/windows-native.js';
const n = windowsNative(), owner = n.createJob(512 * 1024 * 1024, 1024 * 1024 * 1024, 32);
const root = fileURLToPath(new URL('../../../../../', import.meta.url));
const env = Object.fromEntries(Object.entries(process.env).filter(([k, v]) =>
  v !== undefined && !/KEY|TOKEN|SECRET|PASSWORD|NODE_OPTIONS|^DSH_/i.test(k)));
let child, output = '', stderr = '', expired = false;
try {
  child = n.spawn([process.execPath, fileURLToPath(new URL('./scenario.mjs', import.meta.url)), ...process.argv.slice(2)], root, env, owner.job);
  child.resume(); child.closeInput();
  const end = performance.now() + 25000;
  while (n.exitCode(child.process) === undefined) {
    output += n.read(child.stdout).bytes.toString(); stderr += n.read(child.stderr).bytes.toString();
    if (Buffer.byteLength(output) + Buffer.byteLength(stderr) > 262144 || performance.now() >= end) {
      expired = true; n.terminate(owner.job); break;
    }
    await new Promise(r => setTimeout(r, 10));
  }
  output += n.read(child.stdout).bytes.toString(); stderr += n.read(child.stderr).bytes.toString();
  process.stdout.write(output); process.stderr.write(stderr);
  assert.equal(expired, false, 'outer wall/output boundary');
  assert.equal(n.exitCode(child.process), 0, 'isolated P1C scenario failed');
} finally {
  n.terminate(owner.job);
  const end = performance.now() + 3000;
  while (n.count(owner.job) && performance.now() < end) await new Promise(r => setTimeout(r, 10));
  assert.equal(n.count(owner.job), 0, 'outer Job not empty');
  child?.close(); n.close(owner.port); n.close(owner.job);
  console.log('EXTERNAL_JOB_EMPTY');
}
