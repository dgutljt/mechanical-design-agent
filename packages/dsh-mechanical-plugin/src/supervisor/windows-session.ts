// Host owns every local native handle. The in-Job launcher owns a disjoint OS
// handle table. There is no Worker -> host native handle transfer.
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';
import { windowsNative } from './windows-native.js';
export const monotonicNow = () => Number(process.hrtime.bigint()) / 1e6;
export const RUN_MS = 15000, PROBE_MS = 5000, COMPUTE_MS = 10000, REAP_MS = 3000;
export function phaseTransition(previous: string | undefined, next: string) {
  return previous === undefined ? next === 'resolve' : previous === 'resolve' ? next === 'probe'
    : previous === 'probe' ? next === 'resolve' || next === 'compute' : false;
}
// Runner side of the private admission protocol. No engineering phase may run
// before host authorization. Grant deadlines are absolute, never receipt+budget.
export function runnerPhaseControl() {
  const session = JSON.parse(process.env.MECHANICAL_SUPERVISOR_SESSION!);
  delete process.env.MECHANICAL_SUPERVISOR_SESSION;
  let seq = 0, active: any, pending: any, input = '', closed = false, protocolFault = false;
  const fault = (code: string): never => { throw Object.assign(Error(code), { code }); };
  const check = () => {
    if (protocolFault) fault('OUTPUT_INVALID');
    if (monotonicNow() >= Math.min(session.expires, active?.deadline ?? session.expires)) fault('TIMEOUT');
  };
  const send = (value: any) => {
    const frame = { ...value, taskId: session.taskId, seq: ++seq };
    process.stdout.write(JSON.stringify(frame) + '\n'); return frame;
  };
  const rejectPending = (code: string) => {
    if (pending) { const p = pending; pending = undefined; clearTimeout(p.timer); p.reject(Object.assign(Error(code), { code })); }
  };
  const onData = (bytes: Buffer) => {
    try {
      input += bytes.toString('utf8');
      if (Buffer.byteLength(input) > 1024) fault('OUTPUT_INVALID');
      let newline;
      while ((newline = input.indexOf('\n')) !== -1) {
        const value = JSON.parse(input.slice(0, newline)); input = input.slice(newline + 1);
        if (!pending || value.type !== 'grant' || value.taskId !== session.taskId || value.seq !== pending.seq || value.phase !== pending.phase ||
            !Number.isFinite(value.admittedAt) || !Number.isFinite(value.deadline) || value.admittedAt > monotonicNow() ||
            value.requestedAt !== pending.requestedAt || value.deadline !== pending.deadline) fault('OUTPUT_INVALID');
        const p = pending; pending = undefined; clearTimeout(p.timer); active = value;
        try { check(); p.resolve(value); } catch (error) { p.reject(error); }
      }
    } catch { protocolFault = true; rejectPending('OUTPUT_INVALID'); }
  };
  process.stdin.on('data', onData);
  const onEnd = () => rejectPending('OUTPUT_INVALID');
  process.stdin.on('end', onEnd);
  return {
    session, send, check,
    async phase(phase: string) {
      check();
      if (closed || pending || !phaseTransition(active?.phase, phase)) fault('OUTPUT_INVALID');
      const budget = phase === 'probe' ? session.probeMs : phase === 'compute' ? session.computeMs : RUN_MS;
      return new Promise<any>((resolve, reject) => {
        const requestedAt = monotonicNow(), deadline = Math.min(session.expires, requestedAt + budget);
        const frame = { type: 'phase', phase, requestedAt, taskId: session.taskId, seq: seq + 1 };
        const expire = () => {
          if (!pending || pending.seq !== frame.seq) return;
          if (monotonicNow() < deadline) { pending.timer = setTimeout(expire, Math.max(1, Math.ceil(deadline - monotonicNow()))); return; }
          rejectPending('TIMEOUT');
        };
        const timer = setTimeout(expire, Math.max(1, Math.ceil(deadline - monotonicNow())));
        pending = { ...frame, deadline, budget, resolve, reject, timer };
        send(frame);
      });
    },
    close() { closed = true; rejectPending('OUTPUT_INVALID'); process.stdin.off('data', onData); process.stdin.off('end', onEnd); process.stdin.pause(); }
  };
}
export function engineeringEnvironment() {
  const names = new Set(['SYSTEMROOT', 'WINDIR', 'PATH', 'PATHEXT', 'TEMP', 'TMP', 'USERPROFILE',
    'HOMEDRIVE', 'HOMEPATH', 'LOCALAPPDATA', 'APPDATA', 'VIRTUAL_ENV', 'CONDA_PREFIX', 'MECHANICAL_AGENT_PYTHON']);
  return Object.fromEntries(Object.entries(process.env).filter(([k,v]) => v !== undefined && names.has(k.toUpperCase())));
}
// Only host observations on this monotonic clock establish event order. An
// already-aborted signal has no trustworthy historical timestamp.
export function sessionTermination(expires: number, signal: AbortSignal) {
  let deadline = expires, cause: string | undefined;
  const latch = (code?: string) => { if (!cause && code) cause = code; return cause; };
  const observe = () => cause ?? (monotonicNow() >= deadline ? latch('TIMEOUT')
    : signal.aborted ? latch('CANCELLED') : undefined);
  const onAbort = () => { observe(); };
  signal.addEventListener('abort', onAbort, { once: true });
  observe();
  return { latch, observe, setDeadline(value: number) { deadline = Math.min(expires, value); },
    dispose() { signal.removeEventListener('abort', onAbort); } };
}
export function runWindowsSession(options: any, validate: (text: string) => boolean, signal: AbortSignal) {
  const now = monotonicNow;
  const expires = options.expires ?? now() + Math.min(options.runMs ?? RUN_MS, RUN_MS);
  const termination = options.termination ?? sessionTermination(expires, signal);
  const n = windowsNative();
  const cleanupMs = Math.min(options.cleanupMs ?? REAP_MS, REAP_MS);
  const session = { taskId: randomUUID(), createdAt: now(), expires,
    probeMs: Math.min(options.probeMs ?? PROBE_MS, PROBE_MS), computeMs: Math.min(options.computeMs ?? COMPUTE_MS, COMPUTE_MS) };
  let owner: any, child: any, timer: any, deadlineTimer: any, terminal = false, initializing = true;
  let cleanupEnd = 0, phaseEnd = expires, cause: string | undefined, cleanFault = false;
  let input = '', outBytes = 0, errBytes = 0, payload: string | undefined, candidate = false;
  let partialCleanup: (() => void) | undefined;
  let sequence = 0, ready = false, phase: string | undefined, pendingWrites = 0, requestedAt = 0;
  const phaseTrace: any[] = [];
  const decoder = new TextDecoder('utf-8', { fatal: true });
  // A closure retaining the exact live handles is also the explicit BLOCKED
  // recovery capability. Each close removes ownership only after success.
  const recover = () => {
    try {
      if (pendingWrites) return false;
      if (owner?.job && n.count(owner.job) !== 0) return false;
      if (partialCleanup) { partialCleanup(); partialCleanup = undefined; }
      if (child) { child.close(); child = undefined; }
      if (owner?.port) { n.close(owner.port); owner.port = undefined; }
      if (owner?.job) { n.close(owner.job); owner.job = undefined; }
      return true;
    } catch { return false; }
  };
  return new Promise<any>(resolve => {
    const arm = () => {
      clearTimeout(deadlineTimer);
      deadlineTimer = setTimeout(tick, Math.max(1, (cleanupEnd || Math.min(expires, phaseEnd)) - now()));
    };
    const stop = (code?: string) => {
      // Preserve the first execution cause independently of recovery safety.
      const recoveryFault = code === 'REAP_FAILED';
      // Native initialization/errors may return after the last deadline check.
      // Observe first, but retain the independent recovery-fault evidence above.
      code = termination.latch(termination.observe() ?? code);
      if (code && !cause) cause = code;
      if (recoveryFault) cleanFault = true;
      if (cleanupEnd) return;
      // The sole recovery deadline assignment. It is never reset by a crash,
      // a failed query, cancellation, finalization or an explicit retry.
      cleanupEnd = Math.min(now(), expires, code === 'TIMEOUT' ? phaseEnd : expires) + cleanupMs;
      arm();
      try { if (owner) n.terminate(owner.job); } catch { cleanFault = true; }
    };
    const complete = (empty: boolean) => {
      if (terminal) return;
      terminal = true; clearInterval(timer); clearTimeout(deadlineTimer);
      signal.removeEventListener('abort', onAbort);
      if (!options.termination) termination.dispose();
      // Job emptiness is necessary but not sufficient: all local handles must
      // also be confirmed closed. No lost list, double-close or stale handle.
      const released = empty && recover();
      const blocked = !released || cleanFault;
      resolve({ empty: !blocked, success: !blocked && !cause && candidate,
        code: blocked ? 'REAP_FAILED' : cause, recover, recoveryReady: () => true,
        cleanupEnd, handlesClosed: released, phaseTrace, phaseDeadline: phaseEnd, latchedCause: cause });
    };
    const frame = (value: any) => {
      if (cleanupEnd) return;
      // Check the PREVIOUS deadline before examining any later phase/output.
      // A batch of queued frames can never overwrite an expired probe.
      const observed = termination.observe();
      if (observed) { stop(observed); return; }
      if (value?.taskId !== session.taskId) { stop('OUTPUT_INVALID'); return; }
      if (value.type === 'ready' && value.seq === 0 && !ready) { ready = true; return; }
      if (!ready || !Number.isSafeInteger(value.seq) || value.seq !== sequence + 1) { stop('OUTPUT_INVALID'); return; }
      sequence = value.seq;
      if (value.type === 'phase' && payload === undefined && phaseTransition(phase, value.phase)) {
        if (!Number.isFinite(value.requestedAt) || value.requestedAt < session.createdAt || value.requestedAt < requestedAt || value.requestedAt > now()) { stop('OUTPUT_INVALID'); return; }
        const admittedAt = now();
        requestedAt = value.requestedAt;
        phaseEnd = Math.min(expires, requestedAt + (value.phase === 'probe' ? session.probeMs : value.phase === 'compute' ? session.computeMs : RUN_MS));
        termination.setDeadline(phaseEnd);
        if (now() >= phaseEnd) { stop('TIMEOUT'); return; }
        phase = value.phase;
        phaseTrace.push({ phase, seq: sequence, requestedAt, admittedAt, deadline: phaseEnd });
        arm();
        // At most one 512-byte control write is outstanding. It runs through
        // Koffi async WriteFile; neither host timers nor handle lifetime depend
        // on the launcher reading stdin. Reap waits for callback settlement.
        pendingWrites++;
        void n.writeAsync(child.stdin, JSON.stringify({ type: 'grant', taskId: session.taskId, seq: sequence,
          phase, requestedAt, admittedAt, deadline: phaseEnd }) + '\n').then(() => { pendingWrites--; }, () => {
          pendingWrites--; if (!terminal) stop('REAP_FAILED');
        });
      } else if (value?.type === 'failure' && typeof value.code === 'string') stop(value.code);
      else if (value?.type === 'output' && phase === 'compute' && typeof value.payload === 'string' && payload === undefined) payload = value.payload;
      else if (value?.type === 'finished' && phase === 'compute' && payload !== undefined && !candidate) {
        let valid = false;
        try { valid = validate(payload); } catch {}
        if (termination.observe()) stop(termination.observe());
        else if (!valid) stop('OUTPUT_INVALID');
        else candidate = true;
      } else stop('OUTPUT_INVALID');
    };
    function tick() {
      if (terminal) return;
      try {
        const observed = termination.observe();
        if (observed) stop(observed);
        if (!cleanupEnd && owner && n.resourceEvent(owner.port)) stop('RESOURCE_LIMIT');
        if (child && !cleanupEnd) {
          const out = n.read(child.stdout), err = n.read(child.stderr);
          outBytes += out.bytes.length; errBytes += err.bytes.length;
          if (outBytes > 2300000 || errBytes > 16384) stop('OUTPUT_TRUNCATED');
          else {
            input += decoder.decode(out.bytes, { stream: true });
            let newline;
            while (!cleanupEnd && !pendingWrites && (newline = input.indexOf('\n')) !== -1) {
              const line = input.slice(0, newline); input = input.slice(newline + 1);
              frame(JSON.parse(line));
            }
            const exit = n.exitCode(child.process);
            if (!cleanupEnd && !pendingWrites && exit !== undefined && out.closed && err.closed) {
              input += decoder.decode();
              if (input.trim()) stop('OUTPUT_INVALID');
              else if (exit !== 0 || !candidate) stop('REAP_FAILED');
              else if (termination.observe()) stop(termination.observe());
              else stop();
            }
          }
        }
      } catch { stop('REAP_FAILED'); }
      if (cleanupEnd) {
        let empty = !owner;
        try { if (owner) empty = n.count(owner.job) === 0; } catch { cleanFault = true; }
        if (empty && !pendingWrites) complete(true);
        else if (now() >= cleanupEnd) complete(false);
      }
    }
    const onAbort = () => {
      const code = termination.observe();
      // An in-flight initializer has not published all its owned handles yet.
      if (!initializing) { stop(code); tick(); }
    };
    signal.addEventListener('abort', onAbort, { once: true });
    try {
      // No caller callback, module resolution or pipe WriteFile runs here.
      // The only synchronous process work is Win32 creation with CREATE_SUSPENDED
      // and zero-wait queries. All runner/launcher work is outside this host.
      const observed = termination.observe();
      if (observed) { stop(observed); complete(true); return; }
      owner = n.createJob();
      child = n.spawn([process.execPath, '--max-old-space-size=96', fileURLToPath(new URL('./watchdog.js', import.meta.url))],
        options.cwd, { ...(options.env ?? engineeringEnvironment()), MECHANICAL_SUPERVISOR_LAUNCH: JSON.stringify({
          request: options.request, cwd: options.cwd,
          session,
          runnerPath: options.runnerPath ?? fileURLToPath(new URL('./runner.js', import.meta.url)) }) }, owner.job);
      child.resume(); // Control stdin stays open until session teardown.
      timer = setInterval(tick, 10); arm(); tick();
    } catch (e: any) { partialCleanup = e.cleanup; stop(e.code ?? 'ISOLATION_UNAVAILABLE'); timer = setInterval(tick, 10); tick(); }
    finally { initializing = false; }
  });
}
