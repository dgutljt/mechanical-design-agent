import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { getEventListeners } from 'node:events';
import { Worker, parentPort, workerData } from 'node:worker_threads';
import { cpSync, mkdtempSync, readFileSync, writeFileSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';
import { windowsNative, PROCESS_BYTES, JOB_BYTES } from '../../../dist/supervisor/windows-native.js';
import { runWindowsSession, engineeringEnvironment, sessionTermination } from '../../../dist/supervisor/windows-session.js';
import { executeOverhung, overhungSupervisorState } from '../../../dist/supervisor/overhung-supervisor.js';
import { preflightOverhungInput } from '../../../dist/contracts/overhung-input.js';
const n=windowsNative(), sleep=ms=>new Promise(r=>setTimeout(r,ms));
const req=createRequire(import.meta.url), nativeReq=createRequire(req.resolve('@deepseek-ai/dsh-win32-process'));
const koffi=nativeReq('koffi'), kernel=koffi.load('kernel32.dll');
const handleCount=kernel.func('__stdcall','GetProcessHandleCount','int',['void *','void *']);
const memoryInfo=kernel.func('__stdcall','K32GetProcessMemoryInfo','int',['void *','void *','uint32']);
const imageName=kernel.func('__stdcall','QueryFullProcessImageNameW','int',['void *','uint32','void *','void *']);
function handles(){const b=Buffer.alloc(4);assert.ok(handleCount(0xffffffffffffffffn,b));return b.readUInt32LE();}
function auditOwnership(native){
 const live=new Map(),closed={};const key=h=>String(typeof h==='bigint'?h:koffi.address(h));
 const add=(h,kind)=>{assert.ok(h);assert.equal(live.has(key(h)),false,'live handle reused');live.set(key(h),kind);};
 for(const [name,kind] of [['createJob','job'],['createPort','completion-port']]){
  const fn=native.api[name];native.api[name]=(...a)=>{const h=fn(...a);if(h)add(h,kind);return h;};
 }
 const pipe=native.api.createPipe;native.api.createPipe=(...a)=>{const ok=pipe(...a);if(ok){add(a[0].readBigUInt64LE(),'pipe');add(a[1].readBigUInt64LE(),'pipe');}return ok;};
 const spawn=native.api.createProcess;native.api.createProcess=(...a)=>{const ok=spawn(...a);if(ok){const b=a.at(-1);add(b.readBigUInt64LE(),'process');add(b.readBigUInt64LE(8),'thread');}return ok;};
 const close=native.api.close;native.api.close=h=>{const k=key(h);assert.equal(live.has(k),true,'unowned/double/stale close');const ok=close(h);if(ok){const kind=live.get(k);closed[kind]=(closed[kind]??0)+1;live.delete(k);}return ok;};
 return {live,closed};
}
const root=fileURLToPath(new URL('../../../../../',import.meta.url));
const plugin=fileURLToPath(new URL('../../../',import.meta.url));
const python=process.env.MECHANICAL_AGENT_TEST_PYTHON;
const config={repositoryRoot:root,pythonExecutable:python};
const input={power_kw:5.5,speed_rpm:960,support_span_mm:600,left_overhang_mm:100,right_overhang_mm:100,plane_1_loads:[{load_n:-0,position_mm:-0}],plane_2_loads:[],allowable_shear_mpa:40,assume_constant_torque_over_shaft:true};
const safeFailure=(value,code)=>{assert.equal(value.ok,false);assert.equal(value.error.code,code);assert.equal('results' in value,false);assert.equal('lineage' in value,false);assert.doesNotMatch(JSON.stringify(value),/Traceback|python\.exe|Users[\\/]|SECRET_MARKER/);};
async function fixture(mode, options={}, controller=new AbortController(), validate=()=>true){
 const result=await runWindowsSession({request:JSON.stringify({mode}),cwd:root,runnerPath:fileURLToPath(new URL('./fixture-runner.mjs',import.meta.url)),env:{...engineeringEnvironment(),MECHANICAL_AGENT_TEST_PYTHON:python},runMs:1200,probeMs:250,computeMs:300,...options},validate,controller.signal);
 assert.equal(result.empty,true);assert.equal(result.handlesClosed,true);assert.equal(result.recover(),true);return result;
}
async function nativePython(code,processBytes=PROCESS_BYTES,jobBytes=JOB_BYTES){
 const owner=n.createJob(processBytes,jobBytes), child=n.spawn([python,'-c',code],root,engineeringEnvironment(),owner.job);
 assert.equal(n.member(child.process,owner.job),true);assert.equal(n.count(owner.job),1);assert.equal(n.read(child.stdout).bytes.length,0);
 let output='',limited=false;const until=Date.now()+6000;
 try{child.resume();child.closeInput();while(n.exitCode(child.process)===undefined){output+=n.read(child.stdout).bytes.toString();n.read(child.stderr);limited ||=n.resourceEvent(owner.port);assert.ok(Date.now()<until);await sleep(10)}output+=n.read(child.stdout).bytes.toString();limited ||=n.resourceEvent(owner.port);return {output,limited,limits:n.limits(owner.job)};}
 finally{n.terminate(owner.job);for(let i=0;i<300&&n.count(owner.job);i++)await sleep(10);assert.equal(n.count(owner.job),0);child.close();n.close(owner.port);n.close(owner.job)}
}
async function mutatedBundle(changes){
 const dir=mkdtempSync(join(tmpdir(),'mechanical-supervisor-fault-'));cpSync(join(plugin,'dist'),join(dir,'dist'),{recursive:true});symlinkSync(join(plugin,'node_modules'),join(dir,'node_modules'),'junction');
 writeFileSync(join(dir,'package.json'),'{"type":"module"}');
 for(const [file,from,to] of changes){const path=join(dir,'dist','supervisor',file),source=readFileSync(path,'utf8').replaceAll('\r\n','\n');assert.ok(source.includes(from),'fault injection anchor missing');writeFileSync(path,source.replace(from,to));}
 const api=await import(pathToFileURL(join(dir,'dist/supervisor/overhung-supervisor.js')).href);
 const native=await import(pathToFileURL(join(dir,'dist/supervisor/windows-native.js')).href);
 const session=await import(pathToFileURL(join(dir,'dist/supervisor/windows-session.js')).href);
 return {...api,native:native.windowsNative,runSession:session.runWindowsSession,dir};
}
async function directedSession(api,request,options={}){
 const result=await api.runSession({request:JSON.stringify(request),cwd:root,
  runnerPath:fileURLToPath(new URL('./fixture-runner.mjs',import.meta.url)),
  env:{...engineeringEnvironment(),MECHANICAL_AGENT_TEST_PYTHON:python},runMs:3000,probeMs:200,computeMs:1000,...options},()=>true,new AbortController().signal);
 assert.equal(result.empty,true);assert.equal(result.handlesClosed,true);assert.equal(result.recover(),true);return result;
}
const mode=process.argv[2];
if(mode==='owner-suspended'||mode==='owner-resumed'){
 const own=n.createJob(), child=n.spawn([python,'-c','import time;time.sleep(5)'],root,engineeringEnvironment(),own.job);
 if(mode==='owner-resumed')child.resume();console.log(child.pid);setInterval(()=>{},1000);
}else if(mode==='a1-memory'){
 const facts=await nativePython(`import ctypes,json\nk=ctypes.WinDLL('kernel32');k.QueryInformationJobObject.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_void_p]\nb=ctypes.create_string_buffer(144);assert k.QueryInformationJobObject(None,9,b,144,None)\nprint(json.dumps(dict(flags=int.from_bytes(b.raw[16:20],'little'),process=int.from_bytes(b.raw[112:120],'little'),job=int.from_bytes(b.raw[120:128],'little'))))`);
 assert.deepEqual(JSON.parse(facts.output),{flags:0x2308,process:PROCESS_BYTES,job:JOB_BYTES});
 const memory=await nativePython('held=[]\ntry:\n for i in range(40):held.append(bytearray(8*1024*1024))\n print("UNBOUNDED")\nexcept MemoryError:print("MEMORY_LIMIT",len(held)*8)');
 assert.match(memory.output,/MEMORY_LIMIT/);assert.equal(memory.limited,true);console.log('REAL_PYTHON_256_MIB',memory.output.trim());
 const aggregate=await fixture('aggregate-memory',{runMs:4000,computeMs:3000});assert.equal(aggregate.code,'RESOURCE_LIMIT');
 const single=await fixture('memory',{runMs:2500});assert.equal(single.code,'RESOURCE_LIMIT');console.log('REAL_RUNNER_PLUS_PYTHON_512_MIB RESOURCE_LIMIT');
}else if(mode==='a1-lifecycle'){
 for(const stage of ['suspended','resumed']){
  const owner=spawn(process.execPath,[import.meta.filename,'owner-'+stage],{stdio:['ignore','pipe','pipe'],windowsHide:true});
  const pid=await new Promise((resolve,reject)=>{let text='';const t=setTimeout(()=>reject(Error('owner startup deadline')),3000);owner.stdout.on('data',b=>{text+=b;if(text.includes('\n')){clearTimeout(t);resolve(Number(text.trim()))}});owner.once('error',reject)});
  const handle=n.api.openProcess(0x100000|0x1000,0,pid);assert.ok(handle);assert.equal(n.exitCode(handle),undefined);owner.kill('SIGKILL');
  for(let i=0;i<300&&n.exitCode(handle)===undefined;i++)await sleep(10);assert.notEqual(n.exitCode(handle),undefined);n.close(handle);console.log('OWNER_KILL_CHILD_DEAD',stage);
 }
 const breakaway=await nativePython(`import subprocess,sys\ntry:\n subprocess.Popen([sys.executable,'-c','import time;time.sleep(1)'],creationflags=0x01000000)\n print('ESCAPED')\nexcept OSError:print('BREAKAWAY_DENIED')`);assert.match(breakaway.output,/BREAKAWAY_DENIED/);
 const o=n.createJob();try{assert.throws(()=>n.spawn([process.execPath,'-e','console.log("must-not-run")'],root,engineeringEnvironment(),123n));assert.equal(n.count(o.job),0)}finally{n.close(o.port);n.close(o.job)}
 const old=n.api.setJob;try{n.api.setJob=()=>0;assert.throws(()=>n.createJob())}finally{n.api.setJob=old}
 const create=n.api.createJob;try{n.api.createJob=()=>null;assert.throws(()=>n.createJob())}finally{n.api.createJob=create}
 console.log('BREAKAWAY_AND_UNAVAILABLE_JOB_REJECTED');
}else if(mode==='public'){
 let starts=0;const create=n.api.createJob;n.api.createJob=(...args)=>{starts++;return create(...args)};
 try{const invalid=await executeOverhung(config,{...input,plane_1_loads:Array(129).fill({load_n:1,position_mm:0})},new AbortController().signal);safeFailure(invalid,'INVALID_TOOL_INPUT');assert.equal(starts,0)}finally{n.api.createJob=create}
 assert.equal(overhungSupervisorState(),'IDLE');
 const value=await executeOverhung(config,input,new AbortController().signal);assert.equal(value.ok,true);assert.equal(Object.is(value.results.statics.plane_1.loads[0].load_n,-0),true);assert.equal(Object.is(value.results.statics.plane_1.loads[0].position_mm,-0),true);
 const adjacent=await executeOverhung(config,{...input,allowable_shear_mpa:1000000000000000100},new AbortController().signal);assert.equal(adjacent.ok,true);assert.equal(adjacent.results.combined.allowable_shear_mpa,1000000000000000100);
 safeFailure(await executeOverhung({...config,pythonExecutable:join(root,'SECRET_MARKER.exe')},input,new AbortController().signal),'PYTHON_RESOLUTION_ERROR');
 const pre=new AbortController();pre.abort();safeFailure(await executeOverhung(config,input,pre.signal),'CANCELLED');assert.equal(overhungSupervisorState(),'IDLE');
 safeFailure(await executeOverhung({...config,pythonExecutable:process.execPath},input,new AbortController().signal),'PROBE_FAILED');
 console.log('PUBLIC_FIXED_ADAPTER_AND_P1A_COMPATIBILITY');
}else if(mode==='concurrency'){
 const values=await Promise.all(Array.from({length:8},()=>executeOverhung(config,input,new AbortController().signal)));
 assert.equal(values.filter(v=>v.ok).length,1);for(const v of values.filter(v=>!v.ok))safeFailure(v,'RESOURCE_BUSY');
 assert.equal(overhungSupervisorState(),'IDLE');assert.equal((await executeOverhung(config,input,new AbortController().signal)).ok,true);console.log('BUSY_7_SUCCESS_1_AND_SLOT_REUSE');
 const barrier=new SharedArrayBuffer(4),workers=Array.from({length:2},()=>new Worker(import.meta.filename,{argv:['contender'],workerData:{barrier}}));
 await Promise.all(workers.map(worker=>new Promise((resolve,reject)=>{worker.once('message',resolve);worker.once('error',reject)})));
 const results=workers.map(worker=>new Promise((resolve,reject)=>{worker.once('message',resolve);worker.once('error',reject)}));
 Atomics.store(new Int32Array(barrier),0,1);Atomics.notify(new Int32Array(barrier),0);
 const competing=await Promise.all(results);assert.equal(competing.filter(v=>v.ok).length,1);assert.equal(competing.filter(v=>v.error?.code==='RESOURCE_BUSY').length,1);console.log('CROSS_WORKER_HOST_SLOT_ONE_SUCCESS_ONE_BUSY');
}else if(mode==='contender'){
 parentPort.postMessage('ready');Atomics.wait(new Int32Array(workerData.barrier),0,0);parentPort.postMessage(await executeOverhung(config,input,new AbortController().signal));parentPort.close();
}else if(mode==='phase-timeouts'){
 for(const phase of ['resolve','probe','compute']){const start=performance.now(),result=await fixture(phase,{runMs:450,probeMs:180,computeMs:180});assert.equal(result.code,'TIMEOUT');assert.ok(performance.now()-start<1800);console.log('PHASE_TIMEOUT_EMPTY',phase)}
 assert.equal((await fixture('multi-probe',{runMs:450,probeMs:250})).code,'TIMEOUT');console.log('MULTIPLE_PROBES_CANNOT_EXTEND_TOTAL_BUDGET');
}else if(mode==='phase-cancellation'){
 for(const phase of ['resolve','probe','compute']){
  const controller=new AbortController(),write=n.writeAsync;let timer,admitted=false;
  n.writeAsync=(h,text)=>{const value=JSON.parse(text);if(value.phase===phase){admitted=true;timer=setTimeout(()=>controller.abort(),60);}return write(h,text);};
  try{assert.equal((await fixture(phase,{runMs:2500,probeMs:1000,computeMs:1000},controller)).code,'CANCELLED');assert.equal(admitted,true);}
  finally{clearTimeout(timer);n.writeAsync=write;}console.log('PHASE_CANCEL_EMPTY',phase);
 }
}else if(mode==='outputs'){
 for(const [test,code] of [['bad-json','OUTPUT_INVALID'],['empty','OUTPUT_INVALID'],['bad-utf8','OUTPUT_INVALID'],['truncated','OUTPUT_TRUNCATED'],['nonzero','PYTHON_PROCESS_ERROR'],['output-nonzero','PYTHON_PROCESS_ERROR']]){assert.equal((await fixture(test,{runMs:2500,computeMs:1800})).code,code);console.log('OUTPUT_FAILURE_EMPTY',test)}
 const controller=new AbortController();const late=await fixture('late',{},controller,()=>{controller.abort();return true});assert.equal(late.success,false);assert.equal(late.code,'CANCELLED');console.log('LATE_SUCCESS_REJECTED');
 const descendants=await fixture('descendants');assert.equal(descendants.success,true);console.log('DESCENDANTS_RECLAIMED_BEFORE_SUCCESS');
}else if(mode==='blocked-recovery'){
 const api=await mutatedBundle([['windows-session.js','empty = n.count(owner.job) === 0','empty = false /* injected observation loss after real termination */'],['windows-session.js','options.cleanupMs ?? REAP_MS','options.cleanupMs ?? 150']]);
 safeFailure(await api.executeOverhung(config,input,new AbortController().signal),'REAP_FAILED');assert.equal(api.overhungSupervisorState(),'BLOCKED');safeFailure(await api.executeOverhung(config,input,new AbortController().signal),'REAP_FAILED');
 const native=api.native(),count=native.count;native.count=()=>{throw Error('observation unavailable')};try{assert.equal(api.recoverOverhungSupervisor(),false);assert.equal(api.overhungSupervisorState(),'BLOCKED')}finally{native.count=count}
 assert.equal(api.recoverOverhungSupervisor(),true);assert.equal(api.recoverOverhungSupervisor(),false);assert.equal(api.overhungSupervisorState(),'IDLE');console.log('BLOCKED_UNTIL_EXPLICIT_VERIFIED_RECOVERY');
}else if(mode==='resolver-real-deadline'){
 const api=await mutatedBundle([['runner.js',"const root = await realpath(request.config.repositoryRoot);","await new Promise(() => { setTimeout(() => {}, 20000); }); const root = await realpath(request.config.repositoryRoot);"]]);
 const start=performance.now();safeFailure(await api.executeOverhung(config,input,new AbortController().signal),'TIMEOUT');const elapsed=performance.now()-start;assert.ok(elapsed>=14800&&elapsed<18000);assert.equal(api.overhungSupervisorState(),'IDLE');console.log('REAL_15_SECOND_DEADLINE',Math.round(elapsed));
}else if(mode==='thread-failure'){
 const api=await mutatedBundle([['watchdog.js',"child.resume();","child.resume(); throw Object.assign(Error('SECRET_MARKER'),{code:'ISOLATION_UNAVAILABLE'});"]]);
 const result=await api.executeOverhung(config,input,new AbortController().signal);safeFailure(result,'ISOLATION_UNAVAILABLE');assert.equal(api.overhungSupervisorState(),'IDLE');console.log('WORKER_START_FAILURE_RECLAIMED');
}else if(mode==='thread-crash'){
 const api=await mutatedBundle([['watchdog.js',"child.resume();","child.resume(); process.exit(77);"]]);
 safeFailure(await api.executeOverhung(config,input,new AbortController().signal),'REAP_FAILED');assert.equal(api.overhungSupervisorState(),'BLOCKED');assert.equal(api.recoverOverhungSupervisor(),true);console.log('DEAD_LAUNCHER_REAPED_AND_EXPLICIT_RECOVERY');
}else if(mode==='finally-failure'){
 const api=await mutatedBundle([['windows-session.js','if (child) { child.close(); child = undefined; }','if (child) { child.close(); child = undefined; throw Error("injected finalizer failure"); }']]);
 safeFailure(await api.executeOverhung(config,input,new AbortController().signal),'REAP_FAILED');assert.equal(api.overhungSupervisorState(),'BLOCKED');assert.equal(api.recoverOverhungSupervisor(),true);console.log('FINALIZER_FAILURE_NEVER_REPORTED_AS_SUCCESS');
}else if(mode==='compute-exit'){
 const api=await mutatedBundle([['runner.js','mechanical_agent.bridge.overhung_two_plane_workflow_adapter','sys']]);
 safeFailure(await api.executeOverhung(config,input,new AbortController().signal),'PYTHON_PROCESS_ERROR');assert.equal(api.overhungSupervisorState(),'IDLE');console.log('REAL_PYTHON_COMPUTE_NONZERO_FAILS_CLOSED');
}else if(mode==='request-binding'){
 const api=await mutatedBundle([['runner.js','if (!probe) n.write(child.stdin, payload);',`if (!probe) n.write(child.stdin, payload.replace('"power_kw":5.5','"power_kw":6.5'));`]]);
 safeFailure(await api.executeOverhung(config,input,new AbortController().signal),'OUTPUT_INVALID');assert.equal(api.overhungSupervisorState(),'IDLE');console.log('VALID_RESPONSE_FOR_OTHER_REQUEST_REJECTED');
}else if(mode==='crash-before-repeat'||mode==='crash-after-repeat'){
 const stage=mode==='crash-before-repeat'?'before':'after';
 const replacement=stage==='before'?'process.exit(77); child.resume();':'child.resume(); process.exit(77);';
 const api=await mutatedBundle([['watchdog.js','child.resume();',replacement]]);
 const native=api.native(),count=native.count,ownership=auditOwnership(native);let emptyProofs=0;
 native.count=job=>{const value=count(job);if(value===0)emptyProofs++;return value;};
 // Warm module/native loading and the one process-scoped semaphore first.
 safeFailure(await api.executeOverhung(config,input,new AbortController().signal),'REAP_FAILED');assert.ok(api.recoverOverhungSupervisor());
 const baseline=handles(),samples=[];
 for(let i=0;i<8;i++){
  safeFailure(await api.executeOverhung(config,input,new AbortController().signal),'REAP_FAILED');
  assert.equal(api.overhungSupervisorState(),'BLOCKED');
  safeFailure(await api.executeOverhung(config,input,new AbortController().signal),'REAP_FAILED');
  assert.equal(api.recoverOverhungSupervisor(),true);assert.equal(api.recoverOverhungSupervisor(),false);
  samples.push(handles());assert.equal(samples.at(-1),baseline,'native host handle growth');assert.equal(ownership.live.size,0,'host owned handle leaked');
 }
 assert.ok(emptyProofs>=9);console.log('CRASH_HANDLES',stage,JSON.stringify({baseline,samples,delta:handles()-baseline,emptyProofs,closed:ownership.closed}));
}else if(mode==='close-failure'){
 const api=await mutatedBundle([]),native=api.native();
 await api.executeOverhung(config,input,new AbortController().signal);const baseline=handles();
 const create=native.createJob,close=native.close;let port,empty=false,fail=true;
 native.createJob=(...a)=>{const o=create(...a);port=o.port;return o;};
 native.close=h=>{if(h===port&&fail){empty=true;throw Error('injected close failure');}return close(h);};
 safeFailure(await api.executeOverhung(config,input,new AbortController().signal),'REAP_FAILED');
 assert.equal(empty,true);assert.equal(api.overhungSupervisorState(),'BLOCKED');
 safeFailure(await api.executeOverhung(config,input,new AbortController().signal),'REAP_FAILED');
 assert.equal(api.recoverOverhungSupervisor(),false);fail=false;
 assert.equal(api.recoverOverhungSupervisor(),true);assert.equal(handles(),baseline);console.log('EMPTY_JOB_CLOSE_FAILURE_BLOCKED_THEN_ALL_HANDLES_CLOSED');
}else if(mode==='reap-crash-2800'){
 const api=await mutatedBundle([
  ['overhung-supervisor.js','monotonicNow() + RUN_MS','monotonicNow() + 250'],
  ['watchdog.js','child.resume();','child.resume(); setTimeout(() => process.exit(77), 2950); await new Promise(() => {});']
 ]);
 const native=api.native(),terminate=native.terminate,count=native.count,exit=native.exitCode,spawn=native.spawn;
 let job,launcher,stopAt,crashAt;
 native.spawn=(...a)=>{launcher=spawn(...a);return launcher;};
 native.terminate=h=>{job=h;stopAt??=performance.now();}; // Keep the launcher alive during the first recovery interval.
 native.count=h=>{if(launcher&&exit(launcher.process)!==undefined)crashAt??=performance.now();return 1;};
 const start=performance.now();safeFailure(await api.executeOverhung(config,input,new AbortController().signal),'REAP_FAILED');
 const elapsed=performance.now()-start;
 assert.ok(crashAt&&crashAt-stopAt>2600&&crashAt-stopAt<3050,JSON.stringify({crash:crashAt-stopAt,elapsed}));
 assert.ok(elapsed<3700,'cleanup deadline was reset');assert.equal(api.overhungSupervisorState(),'BLOCKED');
 native.terminate=terminate;native.count=count;terminate(job);
 for(let i=0;i<200&&count(job);i++)await sleep(10);
 assert.equal(api.recoverOverhungSupervisor(),true);console.log('REAP_CRASH_2800',JSON.stringify({crashAfterReapMs:Math.round(crashAt-stopAt),totalMs:Math.round(elapsed)}));
}else if(mode==='launcher-init-stall'||mode==='launcher-watchdog-stall'){
 const anchor=mode==='launcher-init-stall'?"send({ type: 'ready', taskId: session.taskId, seq: 0 });":'child.resume();';
 const api=await mutatedBundle([
  ['overhung-supervisor.js','monotonicNow() + RUN_MS','monotonicNow() + 500'],
  ['watchdog.js',anchor,anchor+(mode==='launcher-watchdog-stall'?' while (true) {}':' await new Promise(() => { setInterval(() => {}, 1000); });')]
 ]);
 const start=performance.now();safeFailure(await api.executeOverhung(config,input,new AbortController().signal),'TIMEOUT');
 assert.ok(performance.now()-start<1800);assert.equal(api.overhungSupervisorState(),'IDLE');console.log('HOST_INDEPENDENT_TAKEOVER',mode,Math.round(performance.now()-start));
}else if(mode==='takeover-race'){
 for(let i=0;i<8;i++){
  const controller=new AbortController();let validations=0;
  const result=await fixture('late',{runMs:600},controller,()=>{validations++;controller.abort();return true;});
  assert.equal(validations,1);assert.equal(result.success,false);assert.equal(result.code,'CANCELLED');assert.equal(result.recover(),true);
 }
 console.log('TAKEOVER_AT_VALIDATION_NO_LATE_SUCCESS_REPEAT_8');
}else if(mode==='cancel-timeout-reap-race'){
 const api=await mutatedBundle([['overhung-supervisor.js','monotonicNow() + RUN_MS','monotonicNow() + 180'],['windows-session.js','options.cleanupMs ?? REAP_MS','options.cleanupMs ?? 180']]);
 const native=api.native(),count=native.count;native.count=()=>{throw Error('observation unavailable');};
 const controller=new AbortController(),t=setTimeout(()=>controller.abort(),175),start=performance.now();
 try{safeFailure(await api.executeOverhung(config,input,controller.signal),'REAP_FAILED');}finally{clearTimeout(t);}
 assert.ok(performance.now()-start<1300);assert.equal(api.overhungSupervisorState(),'BLOCKED');
 safeFailure(await api.executeOverhung(config,input,new AbortController().signal),'REAP_FAILED');assert.equal(api.recoverOverhungSupervisor(),false);
 native.count=count;assert.equal(api.recoverOverhungSupervisor(),true);console.log('CANCEL_TIMEOUT_OBSERVATION_FAILURE_SINGLE_DEADLINE_BLOCKED_RECOVERED');
}else if(mode==='preflight-budget'){
 const api=await mutatedBundle([['overhung-supervisor.js','monotonicNow() + RUN_MS','monotonicNow() + 60'],
  ['overhung-supervisor.js','prepared = preflightOverhungInput(bounded);','{const until=performance.now()+100;while(performance.now()<until){} } prepared = preflightOverhungInput(bounded);']]);
 const native=api.native(),create=native.createJob;let starts=0;native.createJob=(...a)=>{starts++;return create(...a);};
 safeFailure(await api.executeOverhung(config,input,new AbortController().signal),'TIMEOUT');assert.equal(starts,0);assert.equal(api.overhungSupervisorState(),'IDLE');
 const getter={...input};Object.defineProperty(getter,'power_kw',{enumerable:true,get(){throw Error('getter must not run');}});
 safeFailure(await executeOverhung(config,getter,new AbortController().signal),'INVALID_TOOL_INPUT');
 safeFailure(await executeOverhung(config,new Proxy(input,{ownKeys(){throw Error('proxy must not run');}}),new AbortController().signal),'INVALID_TOOL_INPUT');
 console.log('PREFLIGHT_INCLUDED_IN_TOTAL_DEADLINE_NO_ACCESSOR_PROXY_EXECUTION');
}else if(mode==='init-reviewer-short'||mode==='init-reviewer-15000'||mode==='init-races'){
 const realBudget=mode==='init-reviewer-15000',budget=realBudget?15000:160;
 const changes=[
  ['overhung-supervisor.js','const termination = sessionTermination(expires, signal);','const termination = sessionTermination(expires, signal); globalThis.__initStarted?.(expires);'],
  ['windows-session.js','resolve({ empty: !blocked,','const outcome = { empty: !blocked,'],
  ['windows-session.js','latchedCause: cause });','latchedCause: cause }; globalThis.__initSnapshot = outcome; resolve(outcome);']
 ];
 if(!realBudget)changes.push(['overhung-supervisor.js','monotonicNow() + RUN_MS','monotonicNow() + 160']);
 const api=await mutatedBundle(changes),native=api.native(),acquire=native.acquireSlot,create=native.createJob,release=native.releaseSlot;
 const clock=()=>Number(process.hrtime.bigint())/1e6,spinUntil=end=>{while(clock()<end){}};
 let starts=0;native.createJob=(...a)=>{starts++;return create(...a);};
 const kinds=mode==='init-races'?['cancel-locked','before-15','before-1','at','after-1','after-15','deadline-only','acquire-false','acquire-error','timeout-release-failure','cancel-release-failure']:
  Array(realBudget?1:4).fill('expired-then-cancel');
 for(const kind of kinds){
  const controller=new AbortController();let deadline,observedAt,acquiredAt,returnedAt;
  globalThis.__initStarted=end=>{deadline=end;};
  native.acquireSlot=h=>{
   // Faults occur before a Session/Job exists. The real semaphore is still
   // acquired and released on every successful-acquisition path.
   if(kind==='acquire-false'||kind==='acquire-error'){
    spinUntil(deadline+5);controller.abort();
    if(kind==='acquire-error')throw Error('SECRET_MARKER acquisition');return false;
   }
   const ok=acquire(h);assert.equal(ok,true);acquiredAt=clock();
   if(kind==='cancel-locked'||kind==='cancel-release-failure'){observedAt=clock();controller.abort();spinUntil(deadline+5);}
   else if(kind.startsWith('before-')){
    spinUntil(deadline-Number(kind.slice(7)));observedAt=clock();controller.abort();spinUntil(deadline+5);
   }else{
    spinUntil(deadline+(kind==='after-15'?15:kind==='after-1'?1:kind==='at'?0:5));
    if(kind!=='deadline-only'){observedAt=clock();controller.abort();}
   }
   returnedAt=clock();return ok;
  };
  const blocked=kind.endsWith('release-failure');
  native.releaseSlot=blocked?()=>{throw Error('SECRET_MARKER release');}:release;
  delete globalThis.__initSnapshot;
  const begin=clock(),value=await api.executeOverhung(config,input,controller.signal),result=globalThis.__initSnapshot;
  const expected=observedAt!==undefined&&observedAt<deadline?'CANCELLED':'TIMEOUT';
  safeFailure(value,blocked?'REAP_FAILED':expected);assert.deepEqual(Object.keys(value.metadata),[]);assert.equal(starts,0);
  assert.equal(getEventListeners(controller.signal,'abort').length,0);
  if(result){assert.equal(result.latchedCause,expected);assert.equal(result.code,expected);assert.equal(result.success,false);assert.equal(result.empty,true);assert.equal(result.handlesClosed,true);}
  else assert.ok(kind==='acquire-false'||kind==='acquire-error');
  assert.equal(api.overhungSupervisorState(),blocked?'BLOCKED':'IDLE');
  controller.abort();controller.signal.dispatchEvent(new Event('abort'));assert.equal(value.error.code,blocked?'REAP_FAILED':expected);
  if(blocked){
   // A second admission must not replace the first call's diagnostic deadline.
   delete globalThis.__initStarted;
   safeFailure(await api.executeOverhung(config,input,new AbortController().signal),'REAP_FAILED');
   assert.equal(api.recoverOverhungSupervisor(),false);native.releaseSlot=release;assert.equal(api.recoverOverhungSupervisor(),true);
  }
  if(result)assert.equal(result.latchedCause,expected);
  console.log('INITIALIZATION_LATCH',JSON.stringify({kind,budget,expected,session:result?.code,public:value.error.code,
   abortOffsetMs:observedAt===undefined?null:observedAt-deadline,acquireDelayMs:returnedAt===undefined?null:returnedAt-acquiredAt,elapsedMs:clock()-begin}));
 }
 native.acquireSlot=acquire;native.createJob=create;native.releaseSlot=release;
 delete globalThis.__initStarted;delete globalThis.__initSnapshot;
 if(mode==='init-races'){
  // Standalone initialization cannot infer cancellation history from aborted=true.
  for(const recorded of [false,true]){
   const controller=new AbortController(),expires=clock()+50;
   const termination=recorded?sessionTermination(expires,controller.signal):undefined;
   controller.abort();spinUntil(expires+5);
   const result=await runWindowsSession({expires,cwd:root,...(termination?{termination}:{})},()=>{throw Error('must not validate');},controller.signal);
   const expected=recorded?'CANCELLED':'TIMEOUT';
   assert.equal(result.latchedCause,expected);assert.equal(result.code,expected);assert.equal(result.success,false);
   assert.equal(result.empty,true);assert.equal(result.handlesClosed,true);termination?.dispose();
   console.log('INITIALIZATION_ABORT_HISTORY',JSON.stringify({recorded,session:result.code}));
  }
 }
}else if(mode.startsWith('init-exception-')){
 const realBudget=mode==='init-exception-15000',budget=realBudget?15000:mode==='init-exception-native'?300:100;
 const changes=[
  ['overhung-supervisor.js','const termination = sessionTermination(expires, signal);','const termination = sessionTermination(expires, signal); globalThis.__initErrorStarted?.(expires, termination);'],
  ['windows-session.js','resolve({ empty: !blocked,','const outcome = { empty: !blocked,'],
  ['windows-session.js','latchedCause: cause });','latchedCause: cause }; globalThis.__initErrorSnapshot = outcome; resolve(outcome);']
 ];
 if(!realBudget)changes.push(['overhung-supervisor.js','monotonicNow() + RUN_MS','monotonicNow() + '+budget]);
 const api=await mutatedBundle(changes),native=api.native(),clock=()=>Number(process.hrtime.bigint())/1e6;
 const spinUntil=end=>{while(clock()<end){}};
 // Warm the process-scoped semaphore and Koffi async infrastructure before
 // auditing native handles; the short-budget cases never start engineering work.
 assert.equal((await executeOverhung(config,input,new AbortController().signal)).ok,true);
 console.log('INITIALIZATION_EXCEPTION_BEGIN',mode);
 const baseline=handles(),ownership=auditOwnership(native),original={...native},originalApi={...native.api};
 const kinds=mode==='init-exception-native'?['configuration','readback','completion-port','pipe','pipe-handle','process','membership','resume',
   'partial-close-failure','cancel-close-failure','terminate-failure','thread-close-failure']:
  mode==='init-exception-order'?['early','at','after','cancel-first','cancel-late','timeout-latched','other-latched','early-cleanup-late-cancel','reap-error']:
  Array(realBudget?1:4).fill('after');
 const codes=[];
 for(const kind of kinds){
  const controller=new AbortController();let deadline,latch,observedAt,enteredAt,hit=false,thread;
  globalThis.__initErrorStarted=(end,termination)=>{deadline=end;latch=termination;};
  delete globalThis.__initErrorSnapshot;
  const fail=(code='ISOLATION_UNAVAILABLE')=>{
   enteredAt??=clock();assert.ok(enteredAt<deadline,'initial deadline check must pass before the injected delay');hit=true;
   if(kind==='cancel-first'||kind==='cancel-close-failure'){controller.abort();assert.equal(latch.observe(),'CANCELLED');}
   if(kind==='other-latched'){assert.equal(latch.latch('RESOURCE_LIMIT'),'RESOURCE_LIMIT');}
   if(kind!=='early'&&kind!=='early-cleanup-late-cancel')spinUntil(deadline+(kind==='at'?0:10));
   if(kind==='timeout-latched')assert.equal(latch.observe(),'TIMEOUT');
   if(kind==='cancel-late')controller.abort();
   observedAt=clock();
   return Object.assign(Error('SECRET_MARKER initialization'),{code});
  };
  if(mode!=='init-exception-native'){
   native.createJob=()=>{
    const error=fail(kind==='reap-error'?'REAP_FAILED':'ISOLATION_UNAVAILABLE');
    if(kind==='early-cleanup-late-cancel')error.cleanup=()=>{
     spinUntil(deadline+10);controller.abort();controller.signal.dispatchEvent(new Event('abort'));
    };
    throw error;
   };
  }else{
   const delayedFailure=()=>{fail();return 0;};
   if(['configuration','partial-close-failure','cancel-close-failure'].includes(kind))
    native.api.setJob=(...a)=>a[1]===9?delayedFailure():originalApi.setJob(...a);
   if(kind==='readback')native.api.queryJob=(...a)=>a[1]===9?delayedFailure():originalApi.queryJob(...a);
   if(kind==='completion-port')native.api.createPort=()=>{fail();return null;};
   if(kind==='pipe')native.api.createPipe=delayedFailure;
   if(kind==='pipe-handle')native.api.setHandle=delayedFailure;
   if(kind==='process'||kind==='terminate-failure')native.api.createProcess=delayedFailure;
   if(kind==='membership')native.api.inJob=delayedFailure;
   if(kind==='resume')native.api.resume=()=>{fail();return 0xffffffff;};
   if(kind==='partial-close-failure'||kind==='cancel-close-failure')
    native.api.close=()=>{throw Error('SECRET_MARKER close');};
   if(kind==='terminate-failure')native.terminate=h=>{original.terminate(h);throw Error('SECRET_MARKER terminate');};
   if(kind==='thread-close-failure'){
    native.api.createProcess=(...a)=>{const ok=originalApi.createProcess(...a);if(ok)thread=a.at(-1).readBigUInt64LE(8);return ok;};
    native.api.close=h=>{if(h===thread)throw fail('REAP_FAILED');return originalApi.close(h);};
   }
  }
  const begin=clock(),value=await api.executeOverhung(config,input,controller.signal),result=globalThis.__initErrorSnapshot;
  assert.equal(hit,true);assert.ok(result);codes.push(value.error.code);
  const expected=['cancel-first','cancel-close-failure'].includes(kind)?'CANCELLED':kind==='other-latched'?'RESOURCE_LIMIT':
   kind==='early'||kind==='early-cleanup-late-cancel'?'ISOLATION_UNAVAILABLE':'TIMEOUT';
  const blocked=['reap-error','partial-close-failure','cancel-close-failure','terminate-failure','thread-close-failure'].includes(kind);
  // The direct reproducer collects all four old results before its final
  // assertion, so a regression cannot hide repeats behind the first failure.
  const reproducer=mode==='init-exception-short'||realBudget;
  safeFailure(value,reproducer?result.code:blocked?'REAP_FAILED':expected);
  assert.deepEqual(Object.keys(value).sort(),['contract_version','error','metadata','ok','operation']);
  assert.deepEqual(Object.keys(value.error).sort(),['code','message']);assert.deepEqual(Object.keys(value.metadata),[]);
  assert.equal(result.success,false);assert.equal(getEventListeners(controller.signal,'abort').length,0);
  if(!reproducer){assert.equal(result.latchedCause,expected);assert.equal(result.code,blocked?'REAP_FAILED':expected);}
  else assert.equal(result.latchedCause,result.code);
  assert.equal(api.overhungSupervisorState(),blocked?'BLOCKED':'IDLE');
  if(blocked){
   delete globalThis.__initErrorStarted;
   safeFailure(await api.executeOverhung(config,input,new AbortController().signal),'REAP_FAILED');
   if(kind==='partial-close-failure'||kind==='cancel-close-failure')assert.equal(api.recoverOverhungSupervisor(),false);
  }else{assert.equal(result.empty,true);assert.equal(result.handlesClosed,true);}
  Object.assign(native.api,originalApi);Object.assign(native,original);
  if(blocked)assert.equal(api.recoverOverhungSupervisor(),true);
  controller.abort();controller.signal.dispatchEvent(new Event('abort'));
  assert.equal(latch.observe(),result.latchedCause);assert.equal(result.recover(),true);
  assert.equal(api.overhungSupervisorState(),'IDLE');assert.equal(ownership.live.size,0);assert.equal(handles(),baseline);
  console.log('INITIALIZATION_EXCEPTION',JSON.stringify({kind,budget,exceptionOffsetMs:observedAt-deadline,
   elapsedMs:clock()-begin,latched:result.latchedCause,session:result.code,public:value.error.code,blocked,handleDelta:handles()-baseline}));
 }
 delete globalThis.__initErrorStarted;delete globalThis.__initErrorSnapshot;
 if(mode==='init-exception-short'||realBudget)assert.deepEqual(codes,Array(realBudget?1:4).fill('TIMEOUT'));
}else if(mode==='terminal-reviewer-four'){
 const api=await mutatedBundle([
  ['overhung-supervisor.js','monotonicNow() + RUN_MS','monotonicNow() + 220'],
  ['watchdog.js',"send({ type: 'ready', taskId: session.taskId, seq: 0 });","send({ type: 'ready', taskId: session.taskId, seq: 0 }); await new Promise(() => { setInterval(() => {}, 1000); });"],
  ['windows-session.js','resolve({ empty: !blocked,','const outcome = { empty: !blocked,'],
  ['windows-session.js','latchedCause: cause });','latchedCause: cause }; globalThis.__terminalSnapshot = outcome; globalThis.__terminalBeforeResolve?.(); resolve(outcome);']
 ]);
 const codes=[];
 for(let i=0;i<4;i++){
  const controller=new AbortController();globalThis.__terminalBeforeResolve=()=>controller.abort();
  const value=await api.executeOverhung(config,input,controller.signal),result=globalThis.__terminalSnapshot;
  assert.equal(result.latchedCause,'TIMEOUT');assert.equal(result.code,'TIMEOUT');assert.equal(result.success,false);
  assert.equal(result.empty,true);assert.equal(result.handlesClosed,true);assert.equal(controller.signal.aborted,true);
  assert.equal(api.overhungSupervisorState(),'IDLE');codes.push(value.error.code);
  console.log('REVIEWER_TIMEOUT_THEN_CANCEL',i,JSON.stringify({latched:result.latchedCause,session:result.code,public:value.error.code}));
  assert.equal('results' in value,false);assert.equal('lineage' in value,false);
 }
 delete globalThis.__terminalBeforeResolve;delete globalThis.__terminalSnapshot;
 assert.deepEqual(codes,Array(4).fill('TIMEOUT'));
}else if(mode==='terminal-races'){
 const api=await mutatedBundle([
  ['overhung-supervisor.js','monotonicNow() + RUN_MS','monotonicNow() + 320'],
  ['watchdog.js',"send({ type: 'ready', taskId: session.taskId, seq: 0 });","send({ type: 'ready', taskId: session.taskId, seq: 0 }); await new Promise(() => { setInterval(() => {}, 1000); });"],
  ['windows-session.js','if (code && !cause) cause = code;','if (code && !cause) cause = code; globalThis.__terminalOnStop?.(code, cause, expires);'],
  ['windows-session.js',"signal.addEventListener('abort', onAbort, { once: true });\n    try {","signal.addEventListener('abort', onAbort, { once: true }); globalThis.__terminalStarted?.(expires);\n    try {"],
  ['windows-session.js','resolve({ empty: !blocked,','const outcome = { empty: !blocked,'],
  ['windows-session.js','latchedCause: cause });','latchedCause: cause }; globalThis.__terminalSnapshot = outcome; resolve(outcome);']
 ]);
 const native=api.native(),count=native.count,terminate=native.terminate,close=native.close,release=native.releaseSlot;
 // Warm native async/runtime infrastructure before the handle baseline.
 assert.equal((await executeOverhung(config,input,new AbortController().signal)).ok,true);
 console.log('TERMINAL_RACE_BEGIN');
 const baseline=handles(),ownership=auditOwnership(native);
 for(const kind of ['cancel-first','timeout-first','duplicate-cancel','boundary-before','boundary-at','boundary-after',
   'terminate-failure','observation-failure','close-failure','release-failure']){
  const controller=new AbortController();let expected='TIMEOUT',holdUntil=0,abortedAt,deadline,abortTimer,first,releaseAttempts=0,port,failClose=true;
  const abort=()=>{abortedAt??=Number(process.hrtime.bigint())/1e6;controller.abort();};
  globalThis.__terminalStarted=expires=>{
   deadline=expires;
   if(kind==='cancel-first'||kind==='duplicate-cancel'){expected='CANCELLED';abortTimer=setTimeout(abort,30);}
   if(kind.startsWith('boundary-')){
    const offset=kind==='boundary-before'?-30:kind==='boundary-after'?30:0;
    abortTimer=setTimeout(abort,Math.max(1,Math.ceil(expires-Number(process.hrtime.bigint())/1e6)+offset));
   }
  };
  globalThis.__terminalOnStop=(code,cause,expires)=>{
   if(first)return;first=cause;holdUntil=expires+70;
   if(kind==='timeout-first'||kind==='terminate-failure'||kind==='observation-failure'||kind==='close-failure'||kind==='release-failure')queueMicrotask(abort);
   if(kind==='duplicate-cancel')queueMicrotask(()=>{controller.abort();controller.signal.dispatchEvent(new Event('abort'));controller.signal.dispatchEvent(new Event('abort'));});
  };
  let observeFault=true;
  native.count=h=>{
   if(first&&kind==='observation-failure'&&observeFault){observeFault=false;throw Error('SECRET_MARKER query');}
   if(first&&Number(process.hrtime.bigint())/1e6<holdUntil)return 1;
   return count(h);
  };
  native.terminate=h=>{terminate(h);if(kind==='terminate-failure')throw Error('SECRET_MARKER terminate');};
  const create=native.createJob;native.createJob=(...a)=>{const o=create(...a);port=o.port;return o;};
  native.close=h=>{if(kind==='close-failure'&&h===port&&failClose)throw Error('SECRET_MARKER close');return close(h);};
  native.releaseSlot=h=>{releaseAttempts++;if(kind==='release-failure')throw Error('SECRET_MARKER release');return release(h);};
  const value=await api.executeOverhung(config,input,controller.signal),result=globalThis.__terminalSnapshot;
  clearTimeout(abortTimer);
  if(kind.startsWith('boundary-'))expected=abortedAt!==undefined&&abortedAt<deadline?'CANCELLED':'TIMEOUT';
  assert.equal(first,expected);assert.equal(result.latchedCause,expected);assert.equal(result.success,false);
  const blocked=kind.endsWith('failure');
  safeFailure(value,blocked?'REAP_FAILED':expected);assert.deepEqual(Object.keys(value.metadata),[]);
  assert.equal(result.code,blocked&&kind!=='release-failure'?'REAP_FAILED':expected);
  assert.equal(api.overhungSupervisorState(),blocked?'BLOCKED':'IDLE');
  if(blocked){
   safeFailure(await api.executeOverhung(config,input,new AbortController().signal),'REAP_FAILED');
   if(kind==='close-failure')assert.equal(api.recoverOverhungSupervisor(),false);
   if(kind==='release-failure')assert.equal(api.recoverOverhungSupervisor(),false);
  }
  native.count=count;native.terminate=terminate;native.createJob=create;failClose=false;native.close=close;native.releaseSlot=release;
  if(blocked)assert.equal(api.recoverOverhungSupervisor(),true);
  assert.equal(api.overhungSupervisorState(),'IDLE');assert.equal(ownership.live.size,0);assert.equal(handles(),baseline);
  assert.equal(releaseAttempts,kind==='release-failure'?2:blocked?0:1);
  console.log('TERMINAL_RACE',JSON.stringify({kind,latched:result.latchedCause,session:result.code,public:value.error.code,state:api.overhungSupervisorState(),handleDelta:handles()-baseline}));
 }
 delete globalThis.__terminalOnStop;delete globalThis.__terminalStarted;delete globalThis.__terminalSnapshot;
}else if(mode==='terminal-write-failure'){
 const api=await mutatedBundle([
  ['overhung-supervisor.js','monotonicNow() + RUN_MS','monotonicNow() + 1200'],
  ['windows-session.js','if (code && !cause) cause = code;','if (code && !cause) cause = code; globalThis.__terminalOnStop?.(cause);'],
  ['windows-session.js','resolve({ empty: !blocked,','const outcome = { empty: !blocked,'],
  ['windows-session.js','latchedCause: cause });','latchedCause: cause }; globalThis.__terminalSnapshot = outcome; resolve(outcome);']
 ]);
 const native=api.native(),write=native.writeAsync;let rejectWrite;
 native.writeAsync=()=>new Promise((resolve,reject)=>{rejectWrite=reject;});
 globalThis.__terminalOnStop=cause=>{if(cause==='TIMEOUT'&&rejectWrite){const reject=rejectWrite;rejectWrite=undefined;queueMicrotask(()=>reject(Error('SECRET_MARKER write')));}};
 safeFailure(await api.executeOverhung(config,input,new AbortController().signal),'REAP_FAILED');
 const result=globalThis.__terminalSnapshot;assert.equal(result.latchedCause,'TIMEOUT');assert.equal(result.code,'REAP_FAILED');assert.equal(result.handlesClosed,true);
 assert.equal(api.overhungSupervisorState(),'BLOCKED');native.writeAsync=write;assert.equal(api.recoverOverhungSupervisor(),true);
 delete globalThis.__terminalOnStop;delete globalThis.__terminalSnapshot;
 console.log('TERMINAL_TIMEOUT_ASYNC_WRITE_FAILURE_RETAINED_AND_RECOVERED');
}else if(mode==='phase-reviewer-6500'){
 const api=await mutatedBundle([['watchdog.js','send(value);',"if (value.type === 'phase' && value.phase === 'probe') await new Promise(r => setTimeout(r, 6500)); send(value);"]]);
 const start=performance.now(),result=await directedSession(api,{mode:'phase-real-probe',probeSleepMs:5250},{runMs:15000,probeMs:5000,computeMs:10000});
 assert.equal(result.code,'TIMEOUT');assert.equal(result.success,false);assert.equal(result.phaseTrace.some(p=>p.phase==='probe'),false);
 const elapsed=performance.now()-start;assert.ok(elapsed>=6400&&elapsed<9000);
 console.log('REVIEWER_6500_DELAY_5250_PROBE',JSON.stringify({elapsedMs:Math.round(elapsed),code:result.code,probeAdmitted:false}));
}else if(mode==='phase-probe-real-5250'){
 const api=await mutatedBundle([]),start=performance.now();
 const result=await directedSession(api,{mode:'phase-real-probe',probeSleepMs:5250},{runMs:15000,probeMs:5000,computeMs:10000});
 const probe=result.phaseTrace.find(p=>p.phase==='probe'),elapsed=Number(process.hrtime.bigint())/1e6-probe.requestedAt;
 assert.ok(probe);assert.equal(probe.deadline-probe.requestedAt,5000);assert.equal(result.code,'TIMEOUT');assert.equal(result.success,false);
 assert.equal(result.phaseTrace.some(p=>p.phase==='compute'),false);assert.ok(elapsed>=4990&&elapsed<5600);
 console.log('REAL_PYTHON_5250_PROBE_CUTOFF',JSON.stringify({totalMs:Math.round(performance.now()-start),afterProbeMs:Math.round(elapsed),code:result.code}));
}else if(mode==='phase-delayed-reap-budget'){
 const api=await mutatedBundle([['watchdog.js','send(value);',"if (value.type === 'phase' && value.phase === 'probe') await new Promise(r => setTimeout(r, 260)); send(value);"]]);
 const native=api.native(),count=native.count;native.count=()=>1;
 const start=performance.now(),result=await api.runSession({request:JSON.stringify({mode:'phase-real-probe',probeSleepMs:210}),cwd:root,
  runnerPath:fileURLToPath(new URL('./fixture-runner.mjs',import.meta.url)),env:{...engineeringEnvironment(),MECHANICAL_AGENT_TEST_PYTHON:python},
  runMs:3000,probeMs:200,computeMs:1000,cleanupMs:300},()=>true,new AbortController().signal);
 assert.equal(result.code,'REAP_FAILED');assert.equal(result.latchedCause,'TIMEOUT');assert.equal(result.empty,false);
 assert.equal(result.cleanupEnd-result.phaseDeadline,300,'late phase must not obtain a fresh recovery window');
 native.count=count;assert.equal(result.recover(),true);
 console.log('LATE_PHASE_SINGLE_REAP_DEADLINE',JSON.stringify({elapsedMs:Math.round(performance.now()-start),reapBudgetMs:result.cleanupEnd-result.phaseDeadline,latched:result.latchedCause}));
}else if(mode==='phase-scaled-four'){
 const api=await mutatedBundle([['watchdog.js','send(value);',"if (value.type === 'phase' && value.phase === 'probe') await new Promise(r => setTimeout(r, 260)); send(value);"]]);
 for(let i=0;i<4;i++){
  const start=performance.now(),result=await directedSession(api,{mode:'phase-real-probe',probeSleepMs:210});
  assert.equal(result.code,'TIMEOUT');assert.equal(result.success,false);assert.equal(result.phaseTrace.some(p=>p.phase==='probe'),false);
  assert.ok(performance.now()-start>=250);console.log('SCALED_REPLAY_TIMEOUT',i,Math.round(performance.now()-start));
 }
}else if(mode==='phase-boundaries'){
 const api=await mutatedBundle([]);
 for(const offset of [-100,0,30]){
  const result=await directedSession(api,{mode:'phase-real-probe',probeSleepMs:20,boundaryOffset:offset},{probeMs:600});
  assert.equal(result.success,offset<0);if(offset>=0)assert.equal(result.code,'TIMEOUT');
  assert.ok(result.phaseTrace.every(p=>p.deadline<=p.requestedAt+(p.phase==='probe'?600:p.phase==='compute'?1000:15000)));
  console.log('REAL_PROBE_BOUNDARY',offset,result.success?'SUCCESS':result.code);
 }
}else if(mode==='phase-protocol-order'){
 const api=await mutatedBundle([]);
 for(const kind of ['duplicate-seq','duplicate-phase','out-of-order','missing-seq','missing-phase','cross-task','stale']){
  const result=await directedSession(api,{mode:'phase-protocol-'+kind});
  assert.equal(result.success,false);assert.equal(result.code,kind==='stale'?'TIMEOUT':'OUTPUT_INVALID');console.log('PHASE_PROTOCOL_REJECTED',kind,result.code);
 }
 const native=api.native(),write=native.writeAsync;let previousTaskId;
 native.writeAsync=(h,text)=>{previousTaskId??=JSON.parse(text).taskId;return write(h,text);};
 assert.equal((await directedSession(api,{mode:'phase-real-probe',probeSleepMs:20})).success,true);native.writeAsync=write;
 assert.ok(previousTaskId);assert.equal((await directedSession(api,{mode:'phase-protocol-cross-task',replayTaskId:previousTaskId})).code,'OUTPUT_INVALID');
 console.log('ACTUAL_PRIOR_SESSION_PHASE_REPLAY_REJECTED');
}else if(mode==='phase-host-defense'){
 // Disable other timing defenses only in this disposable bundle, so a batch
 // arriving after a real probe overrun exercises host frame admission itself.
 const api=await mutatedBundle([
  ['watchdog.js',"function check() { if (cause) fail(cause); if (now() >= phaseEnd) fail('TIMEOUT'); }",'function check() {}'],
  ['watchdog.js','function arm() {','function arm() { return;'],
  ['windows-session.js',"const observed = termination.observe();\n        if (observed) stop(observed);",'/* injected delayed timer observation */']
 ]);
 for(const late of ['compute','output']){
  const start=performance.now(),result=await directedSession(api,{mode:'phase-real-probe',probeSleepMs:300,late},{probeMs:150});
  assert.equal(result.code,'TIMEOUT');assert.equal(result.success,false);assert.equal(result.phaseTrace.some(p=>p.phase==='compute'),false);
  assert.ok(performance.now()-start>=300);console.log('HOST_PREVIOUS_DEADLINE_GUARD',late,Math.round(performance.now()-start));
 }
}else if(mode==='phase-late-success'){
 const api=await mutatedBundle([]);
 for(const late of ['compute','output']){
  const start=performance.now(),result=await directedSession(api,{mode:'phase-real-probe',probeSleepMs:300,late},{probeMs:180});
  assert.equal(result.success,false);assert.equal(result.code,'TIMEOUT');assert.equal(result.phaseTrace.some(p=>p.phase==='compute'),false);
  assert.ok(performance.now()-start<1400);console.log('EXPIRED_PROBE_LATE_MESSAGE_REJECTED',late);
 }
}else if(mode==='phase-write-recovery'){
 const api=await mutatedBundle([['overhung-supervisor.js','monotonicNow() + RUN_MS','monotonicNow() + 1500']]),native=api.native();
 assert.equal((await api.executeOverhung(config,input,new AbortController().signal)).ok,true);const baseline=handles(),ownership=auditOwnership(native);
 const write=native.writeAsync;let settle;native.writeAsync=()=>new Promise(resolve=>{settle=resolve;});
 const start=performance.now();safeFailure(await api.executeOverhung(config,input,new AbortController().signal),'REAP_FAILED');
 const elapsed=performance.now()-start;assert.ok(elapsed>=4400&&elapsed<5400);assert.equal(api.overhungSupervisorState(),'BLOCKED');
 safeFailure(await api.executeOverhung(config,input,new AbortController().signal),'REAP_FAILED');assert.equal(api.recoverOverhungSupervisor(),false);
 assert.ok(ownership.live.size>0);settle();await sleep(10);native.writeAsync=write;
 assert.equal(api.recoverOverhungSupervisor(),true);assert.equal(ownership.live.size,0);assert.equal(handles(),baseline);
 console.log('PENDING_CONTROL_WRITE_REAP_GUARD',JSON.stringify({totalMs:Math.round(elapsed),delta:handles()-baseline}));
}else if(mode==='normal-handles-repeat'){
 const api=await mutatedBundle([]);assert.equal((await api.executeOverhung(config,input,new AbortController().signal)).ok,true);
 const baseline=handles(),ownership=auditOwnership(api.native()),samples=[];
 for(let i=0;i<4;i++){assert.equal((await api.executeOverhung(config,input,new AbortController().signal)).ok,true);samples.push(handles());assert.equal(samples.at(-1),baseline);assert.equal(ownership.live.size,0);}
 console.log('ASYNC_PHASE_NORMAL_HANDLES',JSON.stringify({baseline,samples,closed:ownership.closed}));
}else if(mode==='inventory'){
 const own=n.createJob(),child=n.spawn([process.execPath,join(plugin,'node_modules/@deepseek-ai/dsh/lib/bin.js'),
  '--profile','headless','--patch',join(root,'.dsh/mechanical-engineering.patch.yml'),'--patch',join(root,'scripts/v15-inventory.patch.yml'),'--json'],
  root,engineeringEnvironment(),own.job);
 const until=performance.now()+8000;let stderr='',stdout='';
 try{
  child.resume(); // Keep stdin open: the headless app waits for input and makes no model request.
  let line;
  while(!line){
   stderr+=n.read(child.stderr).bytes.toString();stdout+=n.read(child.stdout).bytes.toString();
   line=stderr.split(/\r?\n/).find(v=>v.startsWith('ACCEPTANCE_INVENTORY ')&&v.endsWith('}'));
   assert.ok(Buffer.byteLength(stderr)+Buffer.byteLength(stdout)<131072);
   assert.equal(n.exitCode(child.process),undefined,stderr);assert.ok(performance.now()<until,'mounted inventory deadline');await sleep(10);
  }
  const actual=JSON.parse(line.slice('ACCEPTANCE_INVENTORY '.length)),policy=JSON.parse(readFileSync(join(root,'scripts/v15-policy.json'),'utf8'));
  assert.deepEqual(actual.tools,policy.restricted.tools.toSorted());assert.deepEqual(actual.bundles.toSorted(),policy.restricted.bundles.toSorted());
  const version=JSON.parse(readFileSync(join(plugin,'node_modules/@deepseek-ai/dsh/package.json'),'utf8')).version;assert.equal(version,'0.2.0-rc.2');
  console.log('MOUNTED_11_TOOL_INVENTORY_UNCHANGED',JSON.stringify({...actual,version}));
 }finally{
  n.terminate(own.job);for(let i=0;i<300&&n.count(own.job);i++)await sleep(10);assert.equal(n.count(own.job),0);child.close();n.close(own.port);n.close(own.job);
 }
}else if(mode==='memory-native-attempt'){
 const owner=n.createJob(),child=n.spawn([process.execPath,'--max-old-space-size=96',fileURLToPath(new URL('./fixture-runner.mjs',import.meta.url))],root,
  {...engineeringEnvironment(),MECHANICAL_AGENT_TEST_PYTHON:python,MECHANICAL_SUPERVISOR_REQUEST:JSON.stringify({mode:'memory-attempt-accounting'})},owner.job);
 const until=performance.now()+9000;let output='',stderr='';
 try{
  child.resume();child.closeInput();while(n.exitCode(child.process)===undefined){output+=n.read(child.stdout).bytes.toString();stderr+=n.read(child.stderr).bytes.toString();assert.ok(performance.now()<until);await sleep(5);}
  output+=n.read(child.stdout).bytes.toString();stderr+=n.read(child.stderr).bytes.toString();assert.equal(n.exitCode(child.process),0,stderr);
  const facts=JSON.parse(output.split(/\r?\n/).find(s=>s.startsWith('NATIVE_ATTEMPT ')).slice('NATIVE_ATTEMPT '.length));
  const events=[];
  for(let i=0;i<512;i++){
   const message=Buffer.alloc(4),key=Buffer.alloc(8),overlapped=Buffer.alloc(8);
   if(!n.api.portStatus(owner.port,message,key,overlapped,0)){assert.equal(n.api.error(),258);break;}
   events.push(message.readUInt32LE());
  }
  assert.ok(events.includes(10),'aggregate Job memory-limit notification evidence');facts.jobEvents=events;
  assert.equal(facts.denied,true);assert.equal(facts.before.jobLimit,JOB_BYTES);assert.equal(facts.before.processLimit,PROCESS_BYTES);
  assert.ok(facts.before.private+facts.attemptBytes<PROCESS_BYTES);assert.ok(Math.abs(facts.after.private-facts.before.private)<1024*1024);
  console.log('NATIVE_DENIED_ALLOCATION_ACCOUNTING',JSON.stringify(facts));
 }finally{
  n.terminate(owner.job);for(let i=0;i<300&&n.count(owner.job);i++)await sleep(10);assert.equal(n.count(owner.job),0);child.close();n.close(owner.port);n.close(owner.job);
 }
}else if(mode.startsWith('memory-study-')){
 const [, ,quantumText,scheduling]=mode.split('-'),quantumMiB=Number(quantumText),serial=scheduling==='serial';
 assert.ok([1,8,32].includes(quantumMiB));
 const owner=n.createJob(),child=n.spawn([process.execPath,'--max-old-space-size=96',fileURLToPath(new URL('./fixture-runner.mjs',import.meta.url))],root,
  {...engineeringEnvironment(),MECHANICAL_AGENT_TEST_PYTHON:python,MECHANICAL_SUPERVISOR_REQUEST:JSON.stringify({mode:'memory-reserve-study',quantumMiB,serial})},owner.job);
 const until=performance.now()+9000;let maxPeak=0,denied=false,output='',stderr='',maxCount=0;
 try{
  child.resume();child.closeInput();
  while(n.exitCode(child.process)===undefined){
   output+=n.read(child.stdout).bytes.toString();stderr+=n.read(child.stderr).bytes.toString();denied||=n.resourceEvent(owner.port);
   maxPeak=Math.max(maxPeak,n.limits(owner.job).peakJobBytes);maxCount=Math.max(maxCount,n.count(owner.job));assert.ok(performance.now()<until);await sleep(5);
  }
  output+=n.read(child.stdout).bytes.toString();stderr+=n.read(child.stderr).bytes.toString();denied||=n.resourceEvent(owner.port);maxPeak=Math.max(maxPeak,n.limits(owner.job).peakJobBytes);
  const exitCode=n.exitCode(child.process),completedStudy=exitCode===0;
  assert.equal(denied,true,'native resource-limit event required');
  if(completedStudy)assert.match(output,/DENIED/);
  else{assert.ok([134,0x80000003].includes(exitCode),'unknown coordinator failure: '+exitCode);assert.match(stderr,/out of memory/i);}
  const info=Buffer.alloc(48);kernel.func('__stdcall','GetSystemInfo','void',['void *'])(info);
  console.log('MEMORY_RESERVE_STUDY',JSON.stringify({quantumMiB,serial,completedStudy,coordinatorOOM:!completedStudy,exitCode,configuredJob:JOB_BYTES,configuredProcess:PROCESS_BYTES,maxPeak,excessBytes:Math.max(0,maxPeak-JOB_BYTES),maxCount,
   windows:(await import('node:os')).release(),pageBytes:info.readUInt32LE(4),allocationGranularity:info.readUInt32LE(40),allocation:output.trim()}));
 }finally{
  n.terminate(owner.job);for(let i=0;i<300&&n.count(owner.job);i++)await sleep(10);assert.equal(n.count(owner.job),0);child.close();n.close(owner.port);n.close(owner.job);
 }
}else if(mode==='memory-counters'){
 const outer=n.limits(null);console.log('MEMORY_OUTER_LIMITS',JSON.stringify(outer));
 for(let iteration=0;iteration<3;iteration++){
  const owner=n.createJob(),child=n.spawn([process.execPath,fileURLToPath(new URL('./fixture-runner.mjs',import.meta.url))],root,
   {...engineeringEnvironment(),MECHANICAL_AGENT_TEST_PYTHON:python,MECHANICAL_SUPERVISOR_REQUEST:JSON.stringify({mode:'aggregate-memory'})},owner.job);
  let maxPrivate=0,maxPeak=0,maxProcesses=0,samples=0,denied=false;const images=new Set();const until=performance.now()+7000;
  try{
   child.resume();child.closeInput();
   while(n.exitCode(child.process)===undefined){
    n.read(child.stdout);n.read(child.stderr);denied||=n.resourceEvent(owner.port);
    const ids=Buffer.alloc(8+8*64);assert.ok(n.api.queryJob(owner.job,3,ids,ids.length,null));
    const number=ids.readUInt32LE(4);maxProcesses=Math.max(maxProcesses,number);let total=0;
    for(let i=0;i<number;i++){
     const h=n.api.openProcess(0x1000|0x10,0,Number(ids.readBigUInt64LE(8+i*8)));if(!h)continue;
     try{const info=Buffer.alloc(80);info.writeUInt32LE(80);if(memoryInfo(h,info,80))total+=Number(info.readBigUInt64LE(72));
      const path=Buffer.alloc(2048),size=Buffer.alloc(4);size.writeUInt32LE(1024);if(imageName(h,0,path,size))images.add(path.subarray(0,size.readUInt32LE()*2).toString('utf16le').split('\\').at(-1));
     }finally{n.close(h);}
    }
    maxPrivate=Math.max(maxPrivate,total);maxPeak=Math.max(maxPeak,n.limits(owner.job).peakJobBytes);samples++;
    assert.ok(performance.now()<until);await sleep(5);
   }
   maxPeak=Math.max(maxPeak,n.limits(owner.job).peakJobBytes);denied||=n.resourceEvent(owner.port);
   assert.equal(denied,true);console.log('MEMORY_COUNTERS',JSON.stringify({iteration,limit:JOB_BYTES,maxPeak,maxPrivate,maxProcesses,images:[...images],samples,denied,outerLimit:outer.jobBytes}));
  }finally{
   n.terminate(owner.job);for(let i=0;i<300&&n.count(owner.job);i++)await sleep(10);assert.equal(n.count(owner.job),0);child.close();n.close(owner.port);n.close(owner.job);
  }
 }
}else if(mode==='fallback'){
 const api=await mutatedBundle([['windows-native.js',"if (process.platform !== 'win32' || process.arch !== 'x64')",'if (true)']]);
 safeFailure(await api.executeOverhung(config,input,new AbortController().signal),'ISOLATION_UNAVAILABLE');assert.equal(api.overhungSupervisorState(),'IDLE');console.log('NO_WEAKER_FALLBACK');
}else throw Error('Unknown isolated scenario');
