import assert from 'node:assert/strict';
import { test } from 'node:test';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
const guard=fileURLToPath(new URL('./fixtures/supervisor/native-guard.mjs',import.meta.url));
const scenarios=['a1-memory','a1-lifecycle','public','concurrency','phase-timeouts','phase-cancellation','outputs',
  'blocked-recovery','resolver-real-deadline','thread-failure','thread-crash','finally-failure','compute-exit','request-binding','fallback',
  'crash-before-repeat','crash-after-repeat','close-failure','reap-crash-2800','launcher-init-stall','launcher-watchdog-stall',
  'takeover-race','cancel-timeout-reap-race','preflight-budget','memory-counters','inventory',
  'init-reviewer-short','init-reviewer-15000','init-races','init-exception-short','init-exception-15000','init-exception-order','init-exception-native','terminal-reviewer-four','terminal-races','terminal-write-failure','phase-reviewer-6500','phase-probe-real-5250','phase-delayed-reap-budget','phase-scaled-four','phase-boundaries','phase-protocol-order',
  'phase-late-success','phase-host-defense','phase-write-recovery','normal-handles-repeat',
  'memory-study-1-parallel','memory-study-8-parallel','memory-study-32-parallel',
  'memory-study-1-serial','memory-study-8-serial','memory-study-32-serial','memory-native-attempt'];
const pressure=scenario=>scenario==='a1-memory'||scenario==='memory-counters'||scenario.startsWith('memory-study-')||scenario==='memory-native-attempt';
for(const scenario of scenarios)test('Windows bounded supervisor: '+scenario,{timeout:35000,skip:process.platform!=='win32'?'Windows only':process.env.MECHANICAL_SUPERVISOR_SKIP_MEMORY_PRESSURE==='1'&&pressure(scenario)?'Memory pressure explicitly excluded for this run':false},()=>{
 const result=spawnSync(process.execPath,[guard,scenario],{encoding:'utf8',timeout:30000,maxBuffer:262144,windowsHide:true,
  env:{...process.env,MECHANICAL_AGENT_TEST_PYTHON:process.env.MECHANICAL_AGENT_TEST_PYTHON||process.env.MECHANICAL_AGENT_PYTHON||'python'}});
 assert.equal(result.error,undefined,result.stderr);assert.equal(result.status,0,result.stdout+'\n'+result.stderr);
 assert.match(result.stdout,/EXTERNAL_JOB_EMPTY/);process.stdout.write(result.stdout);
});
