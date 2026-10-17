// Dedicated in-Job launcher PROCESS. Its native handles never enter the host.
// OS process teardown is the trusted finalizer, including abrupt process.exit.
import { windowsNative } from './windows-native.js';
import { monotonicNow as now, phaseTransition, RUN_MS } from './windows-session.js';
const n = windowsNative();
const options = JSON.parse(process.env.MECHANICAL_SUPERVISOR_LAUNCH!);
delete process.env.MECHANICAL_SUPERVISOR_LAUNCH;
const session = options.session;
const send = (value: any) => process.stdout.write(JSON.stringify(value) + '\n');
let child: any, phase: string | undefined, phaseEnd = session.expires, seq = 0, requestedAt = 0;
let pending: any, inputControl = '', phaseTimer: any, cause: string | undefined;
const fail = (code = 'OUTPUT_INVALID'): never => { throw Object.assign(Error(code), { code }); };
function check() { if (cause) fail(cause); if (now() >= phaseEnd) fail('TIMEOUT'); }
function arm() {
  clearTimeout(phaseTimer);
  phaseTimer = setTimeout(() => {
    if (now() < phaseEnd) { arm(); return; }
    cause ??= 'TIMEOUT'; if (child) n.api.terminate(child.process, 1);
  }, Math.max(1, Math.ceil(phaseEnd - now())));
}
function control(bytes: Buffer) {
  try {
    inputControl += bytes.toString('utf8');
    if (Buffer.byteLength(inputControl) > 1024) fail();
    let newline;
    while ((newline = inputControl.indexOf('\n')) !== -1) {
      check();
      const value = JSON.parse(inputControl.slice(0, newline)); inputControl = inputControl.slice(newline + 1);
      if (!pending || value.type !== 'grant' || value.taskId !== session.taskId || value.seq !== pending.seq || value.phase !== pending.phase ||
          value.requestedAt !== pending.requestedAt || value.deadline !== phaseEnd ||
          !Number.isFinite(value.admittedAt) || value.admittedAt > now()) fail();
      pending = undefined;
      // Host has already armed this exact deadline. A launcher pipe write can
      // stall here without preventing host takeover of the entire Job.
      n.write(child.stdin, JSON.stringify(value) + '\n');
    }
  } catch (e: any) { cause ??= e.code ?? 'OUTPUT_INVALID'; }
}
try {
  send({ type: 'ready', taskId: session.taskId, seq: 0 });
  child = n.spawn([process.execPath, '--max-old-space-size=96', options.runnerPath], options.cwd,
    { ...process.env, MECHANICAL_SUPERVISOR_REQUEST: options.request,
      MECHANICAL_SUPERVISOR_SESSION: JSON.stringify(session) } as Record<string, string>);
  // Injection seams cover crashes on either side of ResumeThread.
  child.resume(); // Control stdin stays open until session teardown.
  process.stdin.on('data', control); arm();
  const decoder = new TextDecoder('utf-8', { fatal: true });
  let input = '', outBytes = 0, errBytes = 0, output = false;
  while (true) {
    check();
    const out = n.read(child.stdout), err = n.read(child.stderr);
    outBytes += out.bytes.length; errBytes += err.bytes.length;
    if (outBytes > 2200000 || errBytes > 16384) fail('OUTPUT_TRUNCATED');
    input += decoder.decode(out.bytes, { stream: true });
    let newline;
    while ((newline = input.indexOf('\n')) !== -1) {
      check(); // Previous phase must be alive BEFORE any transition or output.
      const line = input.slice(0, newline); input = input.slice(newline + 1);
      const value = JSON.parse(line);
      if (value?.taskId !== session.taskId || !Number.isSafeInteger(value.seq) || value.seq !== seq + 1) fail();
      if (value.type === 'phase' && !output && !pending && phaseTransition(phase, value.phase)) {
        if (!Number.isFinite(value.requestedAt) || value.requestedAt < session.createdAt || value.requestedAt < requestedAt || value.requestedAt > now()) fail();
        requestedAt = value.requestedAt;
        phaseEnd = Math.min(session.expires, requestedAt + (value.phase === 'probe' ? session.probeMs : value.phase === 'compute' ? session.computeMs : RUN_MS));
        check(); phase = value.phase; pending = value; arm();
      } else if (value.type === 'output' && phase === 'compute' && !pending && typeof value.payload === 'string' && !output) output = true;
      else if (!(value.type === 'failure' && typeof value.code === 'string')) fail();
      seq = value.seq;
      send(value);
    }
    const exit = n.exitCode(child.process);
    if (exit !== undefined && out.closed && err.closed) {
      check(); input += decoder.decode();
      if (exit !== 0) fail('PYTHON_PROCESS_ERROR');
      if (input.trim() || !output) fail();
      child.close(); child = undefined;
      check();
      send({ type: 'finished', taskId: session.taskId, seq: ++seq });
      break;
    }
    await new Promise(r => setTimeout(r, 10));
  }
} catch (e: any) {
  send({ type: 'failure', taskId: session.taskId, seq: ++seq,
    code: ['TIMEOUT', 'OUTPUT_TRUNCATED', 'PYTHON_PROCESS_ERROR', 'ISOLATION_UNAVAILABLE', 'REAP_FAILED'].includes(e.code) ? e.code : 'OUTPUT_INVALID' });
} finally {
  clearTimeout(phaseTimer); process.stdin.off('data', control); process.stdin.pause();
  // No ownership changes: OS teardown still closes every launcher-owned handle.
  try { child?.close(); } catch { send({ type: 'failure', taskId: session.taskId, seq: ++seq, code: 'REAP_FAILED' }); }
}
