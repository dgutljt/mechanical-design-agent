// Deliberately faulty runner, only selected through the private test seam.
import { windowsNative } from '../../../dist/supervisor/windows-native.js';
import { runnerPhaseControl, monotonicNow } from '../../../dist/supervisor/windows-session.js';
const n=windowsNative(), root=process.cwd(), sleep=ms=>new Promise(r=>setTimeout(r,ms));
let text=process.env.MECHANICAL_SUPERVISOR_REQUEST;delete process.env.MECHANICAL_SUPERVISOR_REQUEST;
if(text===undefined){text='';for await(const b of process.stdin)text+=b;}
const request=JSON.parse(text);
const protocol=process.env.MECHANICAL_SUPERVISOR_SESSION?runnerPhaseControl():undefined;
const send=protocol?.send??(value=>console.log(JSON.stringify(value)));
const phase=async name=>protocol?await protocol.phase(name):undefined;
try{
await phase('resolve');
if(!['resolve','probe','compute','multi-probe'].includes(request.mode)&&!request.mode.startsWith('phase-')){
 await phase('probe');await phase('compute');
}
const python=process.env.MECHANICAL_AGENT_TEST_PYTHON;
if(request.mode==='bad-json'){console.log('{bad');}
else if(request.mode==='truncated'){process.stdout.write('x'.repeat(2300000));}
else if(request.mode==='bad-utf8'){process.stdout.write(Buffer.from([0xff,0x0a]));}
else if(request.mode==='empty'){/* no response */}
else if(request.mode==='nonzero'){process.exitCode=7;}
else if(request.mode==='output-nonzero'){send({type:'output',payload:'{}'});process.exitCode=7;}
else if(request.mode==='late'){send({type:'output',payload:'{}'});await sleep(50);}
else if(request.mode==='phase-real-probe'){
 const grant=await phase('probe');
 const child=n.spawn([python,'-c',`import time;time.sleep(${(request.probeSleepMs??5250)/1000})`],root,process.env);child.resume();child.closeInput();
 while(n.exitCode(child.process)===undefined)await sleep(5);child.close();
 if(request.boundaryOffset!==undefined){const target=grant.deadline+request.boundaryOffset;while(monotonicNow()<target)await sleep(1);}
 if(request.late==='output'){send({type:'output',payload:'{}'});}
 else if(request.late==='compute'){
  // Deliberately bypass the runner's local check to test the other supervisors.
  send({type:'phase',phase:'compute',requestedAt:monotonicNow()});send({type:'output',payload:'{}'});
 }else{await phase('compute');send({type:'output',payload:'{}'});}
}
else if(request.mode.startsWith('phase-protocol-')){
 const type=request.mode.slice('phase-protocol-'.length),taskId=protocol.session.taskId;
 if(type==='duplicate-phase')await phase('probe');
 if(type==='stale')await sleep(230);
 const frame={type:'phase',phase:'probe',taskId,seq:2,requestedAt:monotonicNow()};
 if(type==='duplicate-seq')frame.seq=1;
 if(type==='missing-seq')frame.seq=3;
 if(type==='cross-task')frame.taskId=request.replayTaskId??'different-task';
 if(type==='out-of-order')frame.phase='compute';
 if(type==='duplicate-phase')frame.seq=3;
 if(type==='missing-phase'){frame.type='output';frame.payload='{}';delete frame.phase;}
 if(type==='stale')frame.requestedAt-=220;
 console.log(JSON.stringify(frame));await sleep(300);
}
else if(request.mode==='multi-probe'){
 for(let i=0;i<8;i++){
  await phase('probe');
  const child=n.spawn([python,'-c','import time;time.sleep(.08)'],root,process.env);child.resume();child.closeInput();
  while(n.exitCode(child.process)===undefined)await sleep(10);child.close();
  if(i<7)await phase('resolve');
 }
 await phase('compute');
 send({type:'output',payload:'{}'});
}
else if(request.mode==='descendants'){
 const grandchild='import time; time.sleep(5)';
 const childCode=`import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',${JSON.stringify(grandchild)}],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);time.sleep(5)`;
 const child=n.spawn([python,'-c',childCode],root,process.env);child.resume();child.closeInput();
 send({type:'output',payload:'{}'});await sleep(100);child.close();
}else if(request.mode==='memory'){
 const child=n.spawn([python,'-c','held=[]\nfor i in range(40): held.append(bytearray(8*1024*1024))'],root,process.env);child.resume();child.closeInput();
 while(n.exitCode(child.process)===undefined)await sleep(10);
 child.close();send({type:'failure',code:'PYTHON_PROCESS_ERROR'});
}else if(request.mode==='memory-attempt-accounting'){
 const holders=Array.from({length:2},()=>n.spawn([python,'-c',"import time;held=bytearray(192*1024*1024);print('READY',flush=True);time.sleep(2)"],root,process.env));
 const until=monotonicNow()+7000;
 for(const child of holders){child.resume();child.closeInput();let ready='';while(!ready.includes('READY')){ready+=n.read(child.stdout).bytes.toString();if(n.exitCode(child.process)!==undefined||monotonicNow()>until)throw Error('holder setup');await sleep(5);}}
 const code=`import ctypes,json\nk=ctypes.WinDLL('kernel32',use_last_error=True)\nk.QueryInformationJobObject.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_void_p]\nk.K32GetProcessMemoryInfo.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_uint32]\nk.VirtualAlloc.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_uint32,ctypes.c_uint32];k.VirtualAlloc.restype=ctypes.c_void_p\nk.VirtualFree.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_uint32]\ndef facts():\n b=ctypes.create_string_buffer(144);assert k.QueryInformationJobObject(None,9,b,144,None)\n p=ctypes.create_string_buffer(80);assert k.K32GetProcessMemoryInfo(ctypes.c_void_p(-1),p,80)\n return dict(jobPeak=int.from_bytes(b.raw[136:144],'little'),private=int.from_bytes(p.raw[72:80],'little'),processLimit=int.from_bytes(b.raw[112:120],'little'),jobLimit=int.from_bytes(b.raw[120:128],'little'))\nbefore=facts()\npointer=k.VirtualAlloc(None,128*1024*1024,0x3000,4);error=ctypes.get_last_error()\nafter=facts()\nprint(json.dumps(dict(before=before,after=after,denied=not bool(pointer),error=error,attemptBytes=128*1024*1024)),flush=True)\nif pointer:k.VirtualFree(pointer,0,0x8000)`;
 const child=n.spawn([python,'-c',code],root,process.env);child.resume();child.closeInput();let output='';
 while(n.exitCode(child.process)===undefined){output+=n.read(child.stdout).bytes.toString();n.read(child.stderr);if(monotonicNow()>until)throw Error('bounded native allocation');await sleep(5);}
 output+=n.read(child.stdout).bytes.toString();child.close();console.log('NATIVE_ATTEMPT '+output.trim());
 while(holders.some(child=>n.exitCode(child.process)===undefined)){if(monotonicNow()>until)throw Error('bounded holders');await sleep(5);}
 for(const child of holders)child.close();
}else if(request.mode==='memory-reserve-study'){
 const q=request.quantumMiB;
 const code=`import time\nheld=[]\ntry:\n for i in range(${192/q}):held.append(bytearray(${q}*1024*1024))\n print('READY',flush=True)\nexcept MemoryError:print('DENIED',flush=True)\ntime.sleep(1.2)`;
 const children=Array.from({length:3},()=>n.spawn([python,'-c',code],root,process.env));
 const status=new Map(children.map(child=>[child,''])),until=monotonicNow()+7000;
 for(const child of children){
  child.resume();child.closeInput();
  if(request.serial){
   while(!/READY|DENIED/.test(status.get(child))&&n.exitCode(child.process)===undefined){
    status.set(child,status.get(child)+n.read(child.stdout).bytes.toString());n.read(child.stderr);
    if(monotonicNow()>until)throw Error('bounded serial admission');await sleep(5);
   }
  }
 }
 while(children.some(child=>n.exitCode(child.process)===undefined)){
  for(const child of children){status.set(child,status.get(child)+n.read(child.stdout).bytes.toString());n.read(child.stderr);}
  if(monotonicNow()>until)throw Error('bounded memory study');await sleep(5);
 }
 for(const child of children){status.set(child,status.get(child)+n.read(child.stdout).bytes.toString());child.close();}
 console.log('ALLOCATION_STATUS '+JSON.stringify([...status.values()].map(s=>s.trim())));
}else if(request.mode==='aggregate-memory'){
 const code='import time\nheld=[]\nfor i in range(23): held.append(bytearray(8*1024*1024))\ntime.sleep(1)';
 const children=Array.from({length:3},()=>n.spawn([python,'-c',code],root,process.env));
 for(const child of children){child.resume();child.closeInput()}
 while(children.some(c=>n.exitCode(c.process)===undefined))await sleep(10);
 for(const child of children)child.close();send({type:'failure',code:'PYTHON_PROCESS_ERROR'});
}else{
 if(request.mode==='probe'||request.mode==='compute')await phase('probe');
 if(request.mode==='compute')await phase('compute');
 const child=n.spawn([python,'-c','import time;time.sleep(5)'],root,process.env);child.resume();child.closeInput();
 // A promise that never completes must not keep the watchdog from terminating.
 await new Promise(()=>{setTimeout(()=>{},20000)});
}
}catch(e){send({type:'failure',code:e.code??'PYTHON_PROCESS_ERROR'});}
finally{protocol?.close();}
