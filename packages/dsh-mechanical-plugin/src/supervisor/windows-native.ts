// Private Windows x64 ABI seam. No DSH Provider mutation and no fallback.
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
const require = createRequire(import.meta.url);
export const PROCESS_BYTES = 256 * 1024 * 1024;
export const JOB_BYTES = 512 * 1024 * 1024;
export class IsolationError extends Error {
  readonly code: string;
  constructor(code = 'ISOLATION_UNAVAILABLE') { super(code); this.code = code; }
}
let loaded: any;
export function windowsNative() {
  if (loaded) return loaded;
  if (process.platform !== 'win32' || process.arch !== 'x64') throw new IsolationError();
  const nativeRequire = createRequire(require.resolve('@deepseek-ai/dsh-win32-process'));
  if (JSON.parse(readFileSync(require.resolve('@deepseek-ai/dsh-win32-process/package.json'), 'utf8')).version !== '0.2.0-rc.2') throw new IsolationError();
  const koffi = nativeRequire('koffi');
  if (koffi.version !== '3.1.1') throw new IsolationError();
  const kernel = koffi.load('kernel32.dll');
  const bind = (name: string, result: string, args: string[]) => kernel.func('__stdcall', name, result, args);
  const api = {
    close: bind('CloseHandle', 'int', ['void *']),
    error: bind('GetLastError', 'uint32', []),
    createJob: bind('CreateJobObjectW', 'void *', ['void *', 'str16']),
    setJob: bind('SetInformationJobObject', 'int', ['void *', 'int', 'void *', 'uint32']),
    queryJob: bind('QueryInformationJobObject', 'int', ['void *', 'int', 'void *', 'uint32', 'void *']),
    terminateJob: bind('TerminateJobObject', 'int', ['void *', 'uint32']),
    inJob: bind('IsProcessInJob', 'int', ['void *', 'void *', 'void *']),
    initAttributes: bind('InitializeProcThreadAttributeList', 'int', ['void *', 'uint32', 'uint32', 'void *']),
    attribute: bind('UpdateProcThreadAttribute', 'int', ['void *', 'uint32', 'uintptr_t', 'void *', 'size_t', 'void *', 'void *']),
    deleteAttributes: bind('DeleteProcThreadAttributeList', 'void', ['void *']),
    createProcess: bind('CreateProcessW', 'int', ['str16', 'str16', 'void *', 'void *', 'int', 'uint32', 'void *', 'str16', 'void *', 'void *']),
    resume: bind('ResumeThread', 'uint32', ['void *']),
    terminate: bind('TerminateProcess', 'int', ['void *', 'uint32']),
    wait: bind('WaitForSingleObject', 'uint32', ['void *', 'uint32']),
    exitCode: bind('GetExitCodeProcess', 'int', ['void *', 'void *']),
    openProcess: bind('OpenProcess', 'void *', ['uint32', 'int', 'uint32']),
    createSemaphore: bind('CreateSemaphoreW', 'void *', ['void *', 'int32', 'int32', 'str16']),
    releaseSemaphore: bind('ReleaseSemaphore', 'int', ['void *', 'int32', 'void *']),
    createPipe: bind('CreatePipe', 'int', ['void *', 'void *', 'void *', 'uint32']),
    setHandle: bind('SetHandleInformation', 'int', ['void *', 'uint32', 'uint32']),
    peek: bind('PeekNamedPipe', 'int', ['void *', 'void *', 'uint32', 'void *', 'void *', 'void *']),
    read: bind('ReadFile', 'int', ['void *', 'void *', 'uint32', 'void *', 'void *']),
    write: bind('WriteFile', 'int', ['void *', 'void *', 'uint32', 'void *', 'void *']),
    createPort: bind('CreateIoCompletionPort', 'void *', ['void *', 'void *', 'uintptr_t', 'uint32']),
    portStatus: bind('GetQueuedCompletionStatus', 'int', ['void *', 'void *', 'void *', 'void *', 'uint32'])
  };
  const ptr = (value: any) => typeof value === 'bigint' ? value : koffi.address(value);
  const checked = (ok: any, code = 'ISOLATION_UNAVAILABLE') => { if (!ok) throw new IsolationError(code); };
  const close = (handle: any) => { if (handle) checked(api.close(handle), 'REAP_FAILED'); };
  function limits(job: any) {
    const value = Buffer.alloc(144);
    checked(api.queryJob(job, 9, value, value.length, null));
    return { flags: value.readUInt32LE(16), processBytes: Number(value.readBigUInt64LE(112)),
      jobBytes: Number(value.readBigUInt64LE(120)), peakJobBytes: Number(value.readBigUInt64LE(136)) };
  }
  function count(job: any) {
    const value = Buffer.alloc(48);
    checked(api.queryJob(job, 1, value, value.length, null), 'REAP_FAILED');
    return value.readUInt32LE(40);
  }
  function createJob(processBytes = PROCESS_BYTES, jobBytes = JOB_BYTES, activeProcesses = 16) {
    const job = api.createJob(null, null);
    checked(job);
    let port;
    try {
      const value = Buffer.alloc(144);
      value.writeUInt32LE(0x2000 | 0x100 | 0x200 | 0x8, 16); // kill-on-close; commit; count; NO breakaway.
      value.writeUInt32LE(activeProcesses, 40);
      value.writeBigUInt64LE(BigInt(processBytes), 112);
      value.writeBigUInt64LE(BigInt(jobBytes), 120);
      checked(api.setJob(job, 9, value, value.length));
      const actual = limits(job);
      checked(actual.flags === value.readUInt32LE(16) && actual.processBytes === processBytes && actual.jobBytes === jobBytes);
      port = api.createPort(0xffffffffffffffffn, null, 0, 1);
      checked(port);
      const association = Buffer.alloc(16);
      association.writeBigUInt64LE(1n, 0); association.writeBigUInt64LE(ptr(port), 8);
      checked(api.setJob(job, 7, association, association.length));
      return { job, port };
    } catch (e: any) {
      let remainingJob: any = job;
      const cleanup = () => {
        if (port) { close(port); port = undefined; }
        if (remainingJob) { close(remainingJob); remainingJob = undefined; }
      };
      try { cleanup(); } catch { e.cleanup = cleanup; }
      throw e;
    }
  }
  function resourceEvent(port: any) {
    let exceeded = false;
    for (let i = 0; i < 256; i++) {
      const message = Buffer.alloc(4), key = Buffer.alloc(8), overlapped = Buffer.alloc(8);
      if (!api.portStatus(port, message, key, overlapped, 0)) {
        if (api.error() === 258) return exceeded;
        throw new IsolationError('REAP_FAILED');
      }
      if ([3, 9, 10].includes(message.readUInt32LE(0))) exceeded = true;
    }
    return exceeded;
  }
  function quote(value: string) {
    if (value && !/[\s"]/u.test(value)) return value;
    return '"' + value.replace(/(\\*)"/g, '$1$1\\"').replace(/(\\+)$/g, '$1$1') + '"';
  }
  function pipe(childReads: boolean) {
    const r = Buffer.alloc(8), w = Buffer.alloc(8), sa = Buffer.alloc(24);
    sa.writeUInt32LE(24, 0); sa.writeUInt32LE(1, 16);
    checked(api.createPipe(r, w, sa, 65536));
    const read = r.readBigUInt64LE(), write = w.readBigUInt64LE();
    try { checked(api.setHandle(childReads ? write : read, 1, 0)); }
    catch (e: any) {
      const remaining = [read, write];
      const cleanup = () => {
        let failed = false;
        for (const h of [...remaining]) try { close(h); remaining.splice(remaining.indexOf(h), 1); } catch { failed = true; }
        if (failed) throw new IsolationError('REAP_FAILED');
      };
      try { cleanup(); } catch { e.cleanup = cleanup; }
      throw e;
    }
    return { read, write };
  }
  function member(processHandle: any, job: any) {
    const out = Buffer.alloc(4);
    checked(api.inJob(processHandle, job, out), 'ISOLATION_UNAVAILABLE');
    return out.readUInt32LE(0) === 1;
  }
  // Job-list assignment is part of CreateProcess itself. Suspension is an
  // additional verification gate, never a create-then-AssignProcess workaround.
  function spawn(argv: string[], cwd: string, env: Record<string, string>, job?: any) {
    let attributes: Buffer | undefined, initialized = false, processHandle: any, thread: any;
    const handles: any[] = [];
    try {
      const input = pipe(true); handles.push(input.read, input.write);
      const output = pipe(false); handles.push(output.read, output.write);
      const error = pipe(false); handles.push(error.read, error.write);
      const childHandles = Buffer.alloc(24);
      [input.read, output.write, error.write].forEach((h, i) => childHandles.writeBigUInt64LE(h, i * 8));
      const size = Buffer.alloc(8), attributeCount = job ? 2 : 1;
      api.initAttributes(null, attributeCount, 0, size);
      checked(size.readBigUInt64LE() > 0n && size.readBigUInt64LE() < 65536n);
      attributes = Buffer.alloc(Number(size.readBigUInt64LE()));
      checked(api.initAttributes(attributes, attributeCount, 0, size)); initialized = true;
      checked(api.attribute(attributes, 0, 0x20002, childHandles, childHandles.length, null, null));
      const jobs = Buffer.alloc(8);
      if (job) { jobs.writeBigUInt64LE(ptr(job)); checked(api.attribute(attributes, 0, 0x2000d, jobs, 8, null, null)); }
      const startup = Buffer.alloc(112), information = Buffer.alloc(24);
      startup.writeUInt32LE(112, 0); startup.writeUInt32LE(0x101, 60); // USESTDHANDLES | USESHOWWINDOW, SW_HIDE.
      [input.read, output.write, error.write].forEach((h, i) => startup.writeBigUInt64LE(h, 80 + i * 8));
      startup.writeBigUInt64LE(ptr(attributes), 104);
      const environment = Buffer.from(Object.entries(env).sort(([a], [b]) => a.localeCompare(b)).map(([k,v]) => `${k}=${v}\0`).join('') + '\0', 'utf16le');
      checked(api.createProcess(argv[0], argv.map(quote).join(' '), null, null, 1,
        0x80000 | 0x400 | 0x4 | 0x8000000, environment, cwd, startup, information));
      processHandle = information.readBigUInt64LE(0); thread = information.readBigUInt64LE(8);
      checked(processHandle && thread);
      checked(member(processHandle, job ?? null));
      for (const h of [input.read, output.write, error.write]) { close(h); handles.splice(handles.indexOf(h), 1); }
      let resumed = false;
      return { pid: information.readUInt32LE(16), process: processHandle, stdin: input.write,
        stdout: output.read, stderr: error.read,
        closeInput() { const index = handles.indexOf(input.write); if (index !== -1) { close(input.write); handles.splice(index, 1); } },
        resume() { if (resumed) throw new IsolationError(); checked(api.resume(thread) !== 0xffffffff); resumed = true; close(thread); thread = undefined; },
        close() {
          let failed = false;
          for (const h of [...handles]) try { close(h); handles.splice(handles.indexOf(h), 1); } catch { failed = true; }
          try { if (thread) { close(thread); thread = undefined; } } catch { failed = true; }
          try { if (processHandle) { close(processHandle); processHandle = undefined; } } catch { failed = true; }
          if (failed) throw new IsolationError('REAP_FAILED');
        }
      };
    } catch (e: any) {
      // At every point following successful creation the OS already owns the
      // process through a Job, even if this JS process is killed right here.
      const previousCleanup = e.cleanup;
      const cleanup = () => {
        let failed = false;
        try { previousCleanup?.(); } catch { failed = true; }
        if (processHandle) api.terminate(processHandle, 1);
        for (const h of [...handles]) try { close(h); handles.splice(handles.indexOf(h), 1); } catch { failed = true; }
        try { if (thread) { close(thread); thread = undefined; } } catch { failed = true; }
        try { if (processHandle) { close(processHandle); processHandle = undefined; } } catch { failed = true; }
        if (failed) throw new IsolationError('REAP_FAILED');
      };
      try { cleanup(); } catch { e.cleanup = cleanup; }
      throw e;
    } finally { if (initialized) api.deleteAttributes(attributes); }
  }
  function write(handle: any, data: string) {
    const bytes = Buffer.from(data), wrote = Buffer.alloc(4);
    checked(bytes.length <= 60000 && api.write(handle, bytes, bytes.length, wrote, null) && wrote.readUInt32LE() === bytes.length, 'PYTHON_PROCESS_ERROR');
  }
  // Host control writes run off the JS event loop. Callers MUST retain the
  // handle and buffers until callback settlement; a pending write blocks reap.
  function writeAsync(handle: any, data: string) {
    const bytes = Buffer.from(data), wrote = Buffer.alloc(4);
    if (bytes.length > 512) return Promise.reject(new IsolationError());
    return new Promise<void>((resolve, reject) => {
      api.write.async(handle, bytes, bytes.length, wrote, null, (error: any, ok: any) => {
        // Keep both Buffers strongly reachable throughout the native call.
        if (error || !ok || wrote.readUInt32LE() !== bytes.length) reject(new IsolationError('REAP_FAILED'));
        else resolve();
      });
    });
  }
  function read(handle: any) {
    const available = Buffer.alloc(4);
    if (!api.peek(handle, null, 0, null, available, null)) {
      if ([109, 232].includes(api.error())) return { bytes: Buffer.alloc(0), closed: true };
      throw new IsolationError('PYTHON_PROCESS_ERROR');
    }
    const length = Math.min(available.readUInt32LE(), 65536);
    if (!length) return { bytes: Buffer.alloc(0), closed: false };
    const bytes = Buffer.alloc(length), got = Buffer.alloc(4);
    checked(api.read(handle, bytes, bytes.length, got, null), 'PYTHON_PROCESS_ERROR');
    return { bytes: bytes.subarray(0, got.readUInt32LE()), closed: false };
  }
  function exitCode(handle: any) {
    const status = api.wait(handle, 0);
    if (status === 258) return undefined;
    checked(status === 0, 'REAP_FAILED');
    const out = Buffer.alloc(4); checked(api.exitCode(handle, out), 'REAP_FAILED'); return out.readUInt32LE();
  }
  return loaded = { api, createJob, limits, count, resourceEvent, spawn, member, write, writeAsync, read, exitCode, close,
    openSlot() { const handle = api.createSemaphore(null, 1, 1, `Local\\mechanical-agent-overhung-${process.pid}`); checked(handle); return handle; },
    acquireSlot(handle: any) { const result = api.wait(handle, 0); checked(result === 0 || result === 258); return result === 0; },
    releaseSlot(handle: any) { checked(api.releaseSemaphore(handle, 1, null), 'REAP_FAILED'); },
    terminate(job: any) { checked(api.terminateJob(job, 1), 'REAP_FAILED'); } };
}
