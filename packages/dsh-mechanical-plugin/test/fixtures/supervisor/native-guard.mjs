// Test-only independent OS boundary, larger than the product Job under test.
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { windowsNative } from '../../../dist/supervisor/windows-native.js';
const n = windowsNative(), owner = n.createJob(512 * 1024 * 1024, 1024 * 1024 * 1024, 32);
const root = fileURLToPath(new URL('../../../../../', import.meta.url));
const env = Object.fromEntries(Object.entries(process.env).filter(([k,v]) => v !== undefined && !/KEY|TOKEN|SECRET|PASSWORD|NODE_OPTIONS|^DSH_/i.test(k)));
const child = n.spawn([process.execPath, fileURLToPath(new URL('./scenario.mjs', import.meta.url)), process.argv[2]], root, env, owner.job);
const end = Date.now() + 25000; let output = '', stderr = '', expired = false;
try {
  child.resume(); child.closeInput();
  while (n.exitCode(child.process) === undefined) {
    output += n.read(child.stdout).bytes.toString(); stderr += n.read(child.stderr).bytes.toString();
    if (Buffer.byteLength(output) + Buffer.byteLength(stderr) > 131072 || Date.now() >= end) { expired = true; n.terminate(owner.job); break; }
    await new Promise(r => setTimeout(r, 10));
  }
  output += n.read(child.stdout).bytes.toString(); stderr += n.read(child.stderr).bytes.toString();
  if (stderr) process.stderr.write(stderr);
  process.stdout.write(output);
  assert.equal(expired, false, 'independent audit wall/output boundary');
  assert.equal(n.exitCode(child.process), 0, 'isolated scenario failed');
} finally {
  n.terminate(owner.job);
  const until = Date.now() + 3000;
  while (n.count(owner.job) && Date.now() < until) await new Promise(r => setTimeout(r, 10));
  assert.equal(n.count(owner.job), 0, 'independent Job not empty');
  child.close(); n.close(owner.port); n.close(owner.job);
  console.log('EXTERNAL_JOB_EMPTY');
}
