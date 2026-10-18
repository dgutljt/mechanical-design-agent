import assert from 'node:assert/strict';
import { cpSync, mkdtempSync, readFileSync, writeFileSync, symlinkSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { executeOverhung, executeOverhungNative, overhungSupervisorState } from '../../../dist/supervisor/overhung-supervisor.js';
import { preflightOverhungInput, encodeSignedZeroJson } from '../../../dist/contracts/overhung-input.js';
import { validateOverhungResponse } from '../../../dist/contracts/overhung-output.js';
const root = fileURLToPath(new URL('../../../../../', import.meta.url));
const plugin = fileURLToPath(new URL('../../../', import.meta.url));
const config = { repositoryRoot: root, pythonExecutable: process.env.MECHANICAL_AGENT_TEST_PYTHON };
const input = { power_kw: 5.5, speed_rpm: 960, support_span_mm: 600,
  left_overhang_mm: 100, right_overhang_mm: 100, plane_1_loads: [], plane_2_loads: [],
  allowable_shear_mpa: 40, assume_constant_torque_over_shaft: true };
const safeFailure = (value, code) => {
  assert.equal(value.ok, false); assert.equal(value.error.code, code);
  assert.equal('results' in value, false); assert.equal('lineage' in value, false);
  assert.doesNotMatch(encodeSignedZeroJson(value), /Traceback|SECRET_MARKER|Users[\\/]/);
};
async function run(args, api = { executeOverhung, overhungSupervisorState }) {
  const before = encodeSignedZeroJson(args), snapshot = preflightOverhungInput(args);
  const value = await api.executeOverhung(config, args, new AbortController().signal);
  assert.equal(encodeSignedZeroJson(args), before, 'original caller input mutated');
  assert.equal(snapshot.payload, preflightOverhungInput(args).payload, 'original snapshot changed');
  assert.equal(api.overhungSupervisorState(), 'IDLE');
  return value;
}
async function faultyRunner(mutation) {
  const dir = mkdtempSync(join(tmpdir(), 'mechanical-p1c-fault-'));
  cpSync(join(plugin, 'dist'), join(dir, 'dist'), { recursive: true });
  symlinkSync(join(plugin, 'node_modules'), join(dir, 'node_modules'), 'junction');
  writeFileSync(join(dir, 'package.json'), '{"type":"module"}');
  const file = join(dir, 'dist/supervisor/runner.js');
  let source = readFileSync(file, 'utf8').replaceAll('\r\n', '\n');
  // stripTypeScriptTypes preserves whitespace at removed type assertions.
  const match = source.match(/const payload = await run\(python\s*, root, false, prepared.payload\);/);
  assert.ok(match, 'production runner anchor missing');
  source = source.replace("import { preflightOverhungEnvelope }", "import { preflightOverhungEnvelope, encodeSignedZeroJson }");
  source = source.replace(match[0], match[0].replace('const payload', 'let payload') +
    '\n{ const data = JSON.parse(payload); ' + mutation + '; payload = encodeSignedZeroJson(data); }');
  writeFileSync(file, source);
  return { ...await import(pathToFileURL(join(dir, 'dist/supervisor/overhung-supervisor.js')).href), bundle: join(dir, 'dist') };
}
const mode = process.argv[2];
if (mode === 'sorting-normal') {
  const args = { ...input,
    plane_1_loads: [{ load_n: -1000, position_mm: -100 }, { load_n: 500, position_mm: 700 }],
    plane_2_loads: [{ load_n: 200, position_mm: 0 }, { load_n: -300, position_mm: 600 }] };
  const sorted = await run(args); assert.equal(sorted.ok, true); validateOverhungResponse(sorted);
  const reversed = await run({ ...args, plane_1_loads: [...args.plane_1_loads].reverse(),
    plane_2_loads: [...args.plane_2_loads].reverse() });
  assert.equal(reversed.ok, true); assert.deepEqual(reversed, sorted);
  assert.equal(encodeSignedZeroJson(sorted.reviews), encodeSignedZeroJson({ torque: 'PASS', statics: 'PASS', combined: 'PASS' }));
  assert.equal(Object.keys(sorted.provenance).length, 4);
  assert.ok(Object.is(sorted.lineage.torque.exact_value, sorted.results.torque.torque_nm));
  assert.ok(Object.is(sorted.lineage.bending_moment.exact_value, sorted.results.combined.bending_moment_nm));
  console.log('SORTED_REVERSED_BOTH_PLANES_IDENTICAL_REVIEW_PROVENANCE_LINEAGE');
} else if (mode === 'sorting-boundary') {
  const a = { load_n: -0, position_mm: -0 }, b = { load_n: +0, position_mm: +0 };
  const args = { ...input, power_kw: -0, plane_1_loads: [
    { load_n: 1, position_mm: 1 + Number.EPSILON }, a,
    { load_n: -2, position_mm: 0 }, b, { ...a }, { load_n: 3, position_mm: 1 }],
    plane_2_loads: [{ load_n: 5, position_mm: +0 }, { load_n: -4, position_mm: -0 }] };
  const value = await run(args); assert.equal(value.ok, true); validateOverhungResponse(value);
  assert.equal(encodeSignedZeroJson(value.results.statics.plane_1.loads), encodeSignedZeroJson([a, args.plane_1_loads[2], b, a, args.plane_1_loads[5], args.plane_1_loads[0]]));
  assert.equal(encodeSignedZeroJson(value.results.statics.plane_2.loads), encodeSignedZeroJson(args.plane_2_loads));
  assert.ok(Object.is(value.results.torque.power_kw, -0));
  assert.ok(Object.is(value.lineage.torque.exact_value, -0));
  assert.equal(value.results.statics.plane_1.loads.length, 6);
  assert.equal(value.results.statics.plane_1.loads.at(-1).position_mm, 1 + Number.EPSILON);
  console.log('DUPLICATES_STABLE_EQUAL_POSITIONS_SIGNED_ZERO_ADJACENT_BINARY64');
} else if (mode === 'sorting-tamper') {
  const args = { ...input, plane_1_loads: [
    { load_n: -2, position_mm: 10 }, { load_n: 3, position_mm: 10 },
    { load_n: -2, position_mm: 10 }, { load_n: 1, position_mm: 20 }],
    plane_2_loads: [{ load_n: -0, position_mm: -0 }, { load_n: 0, position_mm: +0 }] };
  const mutations = {
    value: 'data.results.statics.plane_1.loads[0].load_n += 1',
    deleteDuplicate: 'data.results.statics.plane_1.loads.splice(2, 1)',
    addDuplicate: 'data.results.statics.plane_1.loads.push({...data.results.statics.plane_1.loads[0]})',
    swapEqual: '[data.results.statics.plane_1.loads[0],data.results.statics.plane_1.loads[1]]=[data.results.statics.plane_1.loads[1],data.results.statics.plane_1.loads[0]]',
    reverseOutput: 'data.results.statics.plane_1.loads.reverse()',
    zeroSign: 'data.results.statics.plane_2.loads[0].load_n=0',
    positionSign: 'data.results.statics.plane_2.loads[0].position_mm=0',
    provenance: 'data.provenance.two_support_overhung_two_plane_point_load_v1.model.calculator_function="forged"',
    lineage: 'data.lineage.torque.exact_value+=1'
  };
  for (const [name, mutation] of Object.entries(mutations)) {
    safeFailure(await run(args, await faultyRunner(mutation)), 'OUTPUT_INVALID');
    console.log('REAL_SUPERVISOR_REJECTED', name);
  }
}
else if (mode === 'config' || mode.startsWith('dsh-')) {
  const { windowsNative } = await import('../../../dist/supervisor/windows-native.js');
  const { engineeringEnvironment } = await import('../../../dist/supervisor/windows-session.js');
  const { spawnSync } = await import('node:child_process');
  const { createHash } = await import('node:crypto');
  const n = windowsNative(), dsh = join(plugin, 'node_modules/@deepseek-ai/dsh/lib/bin.js');
  const version = spawnSync(process.execPath, [dsh, '-V'], { encoding: 'utf8', timeout: 8000, windowsHide: true });
  assert.equal(version.status, 0); assert.equal(version.stdout.trim(), '0.2.0-rc.2');
  const home = mkdtempSync(join(tmpdir(), 'mechanical-p1c-home-'));
  const env = { ...engineeringEnvironment(), DSH_HOME: home, DSH_TELEMETRY_MODE: 'DISABLED',
    MECHANICAL_AGENT_PYTHON: config.pythonExecutable, MECHANICAL_P1C_MODE: mode.slice(4) };
  if (mode === 'config') {
    const policy = JSON.parse(readFileSync(join(root, 'scripts/p1c-policy.json'), 'utf8'));
    const canonical = text => text.split(/\r?\n/).filter(x => !x.trimStart().startsWith('#')).join('\n')
      .replace(/file:\/\/\/[A-Za-z]:\/[^\n]*\/packages\/dsh-mechanical-plugin\/dist\/index\.js/g, 'REPO_NATIVE_PLUGIN')
      .replace(/file:\/\/\/[A-Za-z]:\/[^\n]*\/packages\/dsh-mechanical-plugin\/dist\/overhung-native\.js/g, 'REPO_OVERHUNG_PLUGIN');
    const dumps = ['mechanical-engineering', 'mechanical-overhung'].map(profile => {
      const result = spawnSync(process.execPath, [dsh, '--profile', 'headless', '--patch',
        join(root, '.dsh/' + profile + '.patch.yml'), '--dump-config'], {
        cwd: root, env, encoding: 'utf8', timeout: 8000, windowsHide: true, maxBuffer: 262144
      });
      assert.equal(result.error, undefined); assert.equal(result.status, 0, result.stderr);
      return canonical(result.stdout);
    });
    const hashes = dumps.map(text => createHash('sha256').update(text).digest('hex'));
    assert.equal(hashes[0], policy.legacyConfigSha256);
    const blocks = text => text.match(/^- id: [\s\S]*?(?=^- id: |$(?![\s\S]))/gm);
    const old = blocks(dumps[0]), current = blocks(dumps[1]);
    assert.equal(current.length, old.length + 1);
    assert.deepEqual(current.filter(x => !x.startsWith('- id: mechanical-overhung-native\n')), old);
    for (const id of policy.restrictedPluginIds)
      assert.match(current.find(x => x.startsWith('- id: ' + id + '\n')) || '', /\n  disabled: true(?:\n|$)/);
    assert.equal(hashes[1], policy.configSha256);
    console.log('P1C_CONFIG', JSON.stringify({ legacy: hashes[0], optIn: hashes[1],
      restrictedPluginIds: policy.restrictedPluginIds, extraEntries: ['mechanical-overhung-native'] }));
  } else {
    const task = mode.slice(4), legacy = ['inventory11','legacy11'].includes(task);
    let profile = join(root, '.dsh/' + (legacy ? 'mechanical-engineering' : 'mechanical-overhung') + '.patch.yml');
    const temp = mkdtempSync(join(tmpdir(), 'mechanical-p1c-overlay-'));
    if (['output', 'provenance', 'swap'].includes(task)) {
      const mutation = { output: 'data.results.statics.plane_1.loads[0].load_n+=1',
        provenance: 'data.provenance.two_support_overhung_two_plane_point_load_v1.model.calculator_function="forged"',
        swap: 'data.results.statics.plane_1.loads.reverse()' }[task];
      const api = await faultyRunner(mutation);
      env.MECHANICAL_P1C_BUNDLE = api.bundle;
    }
    if (['timeout', 'cancel', 'parse-timeout', 'serialize-timeout', 'serialize-zero', 'serialize-fields'].includes(task)) {
      const api = await faultyRunner('/* unchanged actual Workflow output */');
      env.MECHANICAL_P1C_BUNDLE = api.bundle;
      const file = join(api.bundle, 'supervisor/overhung-supervisor.js');
      const source = readFileSync(file, 'utf8');
      const anchor = 'if (!Object.hasOwn(messages, code))';
      assert.ok(source.includes(anchor));
      writeFileSync(file, source.replace(anchor,
        "process.stderr.write('P1C_SUPERVISOR_FAILURE ' + JSON.stringify({code}) + '\\n');\n    " + anchor));
      if (['parse-timeout','serialize-timeout','serialize-zero','serialize-fields'].includes(task)) {
        const helper = join(api.bundle, 'contracts/overhung-transport.js');
        let helperSource = readFileSync(helper, 'utf8');
        const inject = (from, to) => { assert.ok(helperSource.includes(from), from); helperSource = helperSource.replace(from,to); };
        if (task === 'parse-timeout') {
          writeFileSync(file, readFileSync(file,'utf8').replaceAll('monotonicNow() + RUN_MS','monotonicNow() + 60'));
          inject('assertUniqueJsonKeys(payload);', '{ const until=performance.now()+100; while(performance.now()<until){} } assertUniqueJsonKeys(payload);');
        }
        if (task === 'serialize-timeout') {
          writeFileSync(file, readFileSync(file,'utf8').replaceAll('monotonicNow() + RUN_MS','monotonicNow() + 1500'));
          inject('const text = encodeSignedZeroJson(safe);', '{ const until=performance.now()+1600; while(performance.now()<until){} } const text = encodeSignedZeroJson(safe);');
        }
        if (task === 'serialize-zero') inject('const text = encodeSignedZeroJson(safe);',
          "const text = encodeSignedZeroJson(safe).replaceAll('-0.0','0.0');");
        if (task === 'serialize-fields') inject('const text = encodeSignedZeroJson(safe);',
          "const copy={...safe}; delete copy.provenance; const text = encodeSignedZeroJson(copy);");
        writeFileSync(helper, helperSource);
      }
      if (task === 'timeout') {
        const runner = join(api.bundle, 'supervisor/runner.js'), source = readFileSync(runner, 'utf8');
        const anchor = 'const root = await realpath(request.config.repositoryRoot);';
        assert.ok(source.includes(anchor));
        writeFileSync(runner, source.replace(anchor, 'await new Promise(() => { setTimeout(() => {}, 20000); }); ' + anchor));
      }
    }
    if (['review-fail', 'review-binding', 'provenance-fail', 'compute-timeout'].includes(task)) {
      const repo = join(temp, 'repo');
      cpSync(join(root, 'src'), join(repo, 'src'), { recursive: true });
      cpSync(join(root, 'knowledge'), join(repo, 'knowledge'), { recursive: true });
      cpSync(join(root, 'pyproject.toml'), join(repo, 'pyproject.toml'));
      const workflow = join(repo, task === 'compute-timeout' ? 'src/mechanical_agent/bridge/overhung_two_plane_workflow_adapter.py' : 'src/mechanical_agent/workflows/verified_overhung_two_plane_shaft_strength.py');
      let source = readFileSync(workflow, 'utf8');
      const anchor = task === 'compute-timeout' ? 'def main():' : task !== 'provenance-fail' ? 'checked = review_bound_engineering_result(deepcopy(data))'
        : 'provenance = {model_id: _provenance(model_id) for model_id in REGISTRY_SOURCES}';
      assert.ok(source.includes(anchor));
      source = source.replace(anchor, task === 'compute-timeout' ? 'def main():\n    import time\n    time.sleep(11)' : task === 'review-fail'
        ? 'checked = review_bound_engineering_result({**deepcopy(data), "torque_nm": 999.0})'
        : task === 'review-binding' ? 'checked = review_bound_engineering_result(asdict(calculate_transmitted_torque(6.0, 960.0)))'
        : 'raise ValueError("injected unavailable Registry")');
      writeFileSync(workflow, source);
      env.MECHANICAL_P1C_REPO = repo;
    }
    if (env.MECHANICAL_P1C_BUNDLE || env.MECHANICAL_P1C_REPO) {
      let text = readFileSync(profile, 'utf8')
        .replace("'../packages/dsh-mechanical-plugin/dist/index.js'", JSON.stringify(join(plugin, 'dist/index.js').replaceAll('\\','/')))
        .replace("'../packages/dsh-mechanical-plugin/dist/overhung-native.js'",
          JSON.stringify(join(env.MECHANICAL_P1C_BUNDLE || join(plugin,'dist'), 'overhung-native.js').replaceAll('\\','/')));
      if (env.MECHANICAL_P1C_REPO) text = text.replaceAll('repositoryRoot: !!js process.cwd()',
        'repositoryRoot: ' + JSON.stringify(env.MECHANICAL_P1C_REPO.replaceAll('\\','/')));
      profile = join(temp, 'profile.yml'); writeFileSync(profile, text);
    }
    const probe = join(temp, 'probe.yml');
    writeFileSync(probe, '- insert:\n    - id: p1c-native-acceptance-probe\n      name: ' +
      JSON.stringify(fileURLToPath(new URL('./dsh-probe.mjs', import.meta.url)).replaceAll('\\', '/')) + '\n');
    const owner = n.createJob(512 * 1024 * 1024, 1024 * 1024 * 1024, 32);
    let child, stderr = '', stdout = '', inventory = false;
    try {
      child = n.spawn([process.execPath, dsh, '--profile', 'headless', '--patch', profile, '--patch', probe, '--json'], root, env, owner.job);
      const start = performance.now(); child.resume();
      while (true) {
        stderr += n.read(child.stderr).bytes.toString(); stdout += n.read(child.stdout).bytes.toString();
        inventory ||= stderr.split(/\r?\n/).some(x => x.startsWith('P1C_INVENTORY ') && x.endsWith('}'));
        assert.ok(Buffer.byteLength(stderr) + Buffer.byteLength(stdout) < 262144, 'bounded DSH output');
        if (stderr.includes('P1C_FAILED ')) throw Error(stderr);
        if (stderr.split(/\r?\n/).some(x => x.startsWith('P1C_DONE ') && x.endsWith('}'))) break;
        assert.equal(n.exitCode(child.process), undefined, stderr);
        if (!inventory) assert.ok(performance.now() - start < 8000, 'historical 8s inventory threshold');
        assert.ok(performance.now() - start < 22500, 'bounded DSH engineering scenario');
        await new Promise(r => setTimeout(r, 10));
      }
      for (const line of stderr.split(/\r?\n/).filter(x => x.startsWith('P1C_'))) console.log(line);
      assert.equal(inventory, true);
      if (task === 'cancel') assert.match(stderr, /P1C_SUPERVISOR_FAILURE {"code":"CANCELLED"}/);
      if (['timeout','parse-timeout','serialize-timeout'].includes(task)) assert.match(stderr, /P1C_SUPERVISOR_FAILURE {"code":"TIMEOUT"}/);
    } finally {
      n.terminate(owner.job);
      const end = performance.now() + 3000;
      while (n.count(owner.job) && performance.now() < end) await new Promise(r => setTimeout(r, 10));
      assert.equal(n.count(owner.job), 0); child?.close(); n.close(owner.port); n.close(owner.job);
      console.log('DSH_JOB_EMPTY');
    }
  }
}

else if (mode === 'reject-config') {
  const { spawnSync } = await import('node:child_process');
  const { engineeringEnvironment } = await import('../../../dist/supervisor/windows-session.js');
  const temp = mkdtempSync(join(tmpdir(), 'mechanical-p1c-reject-'));
  const original = readFileSync(join(root,'.dsh/mechanical-overhung.patch.yml'),'utf8')
    .replace("'../packages/dsh-mechanical-plugin/dist/index.js'", JSON.stringify(join(plugin,'dist/index.js').replaceAll('\\','/')))
    .replace("'../packages/dsh-mechanical-plugin/dist/overhung-native.js'", JSON.stringify(join(plugin,'dist/overhung-native.js').replaceAll('\\','/')));
  for (const kind of ['false','missing','type','load','patch']) {
    let text = original;
    if (kind === 'false') text = text.replace('enableVerifiedOverhung: true','enableVerifiedOverhung: false');
    if (kind === 'missing') text = text.replace('        enableVerifiedOverhung: true','');
    if (kind === 'type') text = text.replace('enableVerifiedOverhung: true','enableVerifiedOverhung: [true]');
    if (kind === 'load') text = text.replace('dist/overhung-native.js','dist/no-such-plugin.js');
    const path = join(temp,kind+'.yml');
    if (kind !== 'patch') writeFileSync(path,text);
    const result = spawnSync(process.execPath,[join(plugin,'node_modules/@deepseek-ai/dsh/lib/bin.js'),
      '--profile','headless','--patch',path,'--json'], { cwd:root,
      env:{...engineeringEnvironment(),DSH_HOME:join(temp,'home-'+kind),DSH_TELEMETRY_MODE:'DISABLED'},
      encoding:'utf8',timeout:8000,maxBuffer:262144,windowsHide:true });
    assert.equal(result.error,undefined,'startup must reject rather than wait on a usable fallback: '+kind);
    assert.notEqual(result.status,0,'bad config silently accepted: '+kind);
    console.log('REAL_DSH_STARTUP_REJECTED',kind,result.status);
  }
}

else if (mode === 'transport-parity') {
  const cases = [
    input,
    {...input,power_kw:-0,plane_1_loads:[{load_n:1,position_mm:1+Number.EPSILON},{load_n:-0,position_mm:-0},{load_n:0,position_mm:0},{load_n:2,position_mm:1}],plane_2_loads:[{load_n:-2,position_mm:0},{load_n:3,position_mm:-0}]},
    {...input,allowable_shear_mpa:1000000000000000100},
    {...input,support_span_mm:1,left_overhang_mm:1,right_overhang_mm:0,plane_1_loads:[{load_n:2*Number.MIN_VALUE,position_mm:.5}]}
  ];
  for (const args of cases) {
    const object = await run(args);
    const payload = preflightOverhungInput(args).payload;
    const carrier = await executeOverhungNative(config,{request_json:payload},new AbortController().signal);
    const string = validateOverhungResponse(JSON.parse(carrier.response_json));
    assert.equal(encodeSignedZeroJson(object),encodeSignedZeroJson(string));
    assert.equal(encodeSignedZeroJson(await executeOverhung(config,payload,new AbortController().signal)),encodeSignedZeroJson(object));
    if(Object.is(args.power_kw,-0)) assert.ok(Object.is(string.results.torque.power_kw,-0));
  }
  let calls=0;
  const proxy=new Proxy({}, {ownKeys(){calls++;throw Error('trap');},getPrototypeOf(){calls++;throw Error('trap');}});
  const accessor={};Object.defineProperty(accessor,'request_json',{enumerable:true,get(){calls++;throw Error('getter');}});
  for(const args of [proxy,accessor,{request_json:1},{request_json:'{}',extra:true}]) {
    const value=await executeOverhungNative(config,args,new AbortController().signal);
    safeFailure(validateOverhungResponse(JSON.parse(value.response_json)),'INVALID_TOOL_INPUT');
  }
  assert.equal(calls,0);
  console.log('OBJECT_STRING_NATIVE_BINARY64_PARITY_PRIVATE_SNAPSHOTS_ZERO_TRAPS');
}
else throw Error('Unknown P1C scenario ' + mode);
