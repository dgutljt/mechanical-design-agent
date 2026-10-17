# New overhung Windows execution contract (P1B, directed repair round 6)

This is a candidate implementation for independent review, **not a P1B PASS**.
`executeOverhung(config, rawArgs, signal)` remains unregistered. No twelfth Tool,
P1C integration, legacy Bridge replacement or dependency installation is included.
The eleven-tool profile, three old engineering registrations, DSH 0.2.0-rc.2,
P1A input/output/signed-zero contracts and Python engineering code are unchanged.

## Process and handle ownership (P1-A)

`watchdog.ts` now builds to a dedicated **launcher process**, not a Node Worker.
The host creates a fresh Job and completion port, then creates this launcher
suspended with `PROC_THREAD_ATTRIBUTE_JOB_LIST`. Job association is atomic with
CreateProcess; membership is checked before ResumeThread. Runner and Python
descendants inherit Job membership without either breakaway flag. This uses the
previously authorized repository-local Windows launcher/supervisor (scope A).

| Resource | Sole close owner | Acquisition and release |
| --- | --- | --- |
| Work Job | Host session closure | Created before launcher; never sent/inherited; close only after zero-active proof and child-handle finalization |
| Completion port | Host session closure | Created/associated before launcher; never inherited; close before Job |
| Launcher process handle | Host `spawn` closure | Returned by CreateProcess; kept until Job empty; close acknowledged before releasing slot |
| Launcher primary thread handle | Host `spawn` closure | Created suspended; close following successful ResumeThread, or retained for error cleanup |
| Six anonymous-pipe handles for launcher | Host `spawn` closure | Child ends closed locally after creation; host stdin stays open for bounded phase grants; remaining ends close after asynchronous writes settle |
| Inherited stdio references in launcher | Launcher OS handle table | Restricted HANDLE_LIST; distinct child references, reclaimed by process teardown |
| Runner process/thread/pipes | Launcher `spawn` closure / Windows | Never copied into host; abrupt launcher exit closes its entire OS handle table, including a suspended runner's thread handle |
| Python process/thread/pipes | Runner `spawn` closure / Windows | Never copied into host; runner termination closes its entire OS handle table |
| Process attribute-list storage | Creating `spawn` call | DeleteProcThreadAttributeList in finally, then JS-owned buffer storage |
| Slot semaphore | Host/plugin owner context | One process-scoped named semaphore, acquired without waiting; reused across calls, closed by OS at host process exit |

There is **no native handle ownership transfer between JS threads** and no
cross-thread close using unverified handle numbers. The host closure retains
each owned handle until CloseHandle succeeds. Partial spawn/Job/pipe failures
retain retry closures; failed close does not splice an unclosed handle out of
its ownership list. The launcher never holds a Job handle, so host death closes
the final Job handle and KILL_ON_JOB_CLOSE also kills launcher and descendants.
The asynchronous control WriteFile temporarily borrows host-owned stdin, without
close ownership. Its callback retains both buffers and decrements an outstanding
call counter. Neither automatic nor explicit finalization can close a borrowed
handle or release the slot until that counter is zero. Unconfirmed completion
at the original recovery deadline returns REAP_FAILED/BLOCKED and retains the
exact ownership closure for later explicit, verified recovery.

Job emptiness alone is insufficient. The host additionally closes its process,
thread, pipe, port and Job handles. An unconfirmed finalizer or observation puts
the slot in BLOCKED. Abrupt launcher exit reports REAP_FAILED and remains BLOCKED
even when automatic cleanup has succeeded; explicit recovery verifies live
resources or uses the recorded sealed empty-and-closed proof. New requests in
BLOCKED are rejected. Failed explicit recovery cannot reset the slot.

The trusted API caller owns the host session context for the whole call. Losing
that context itself (for example forcibly killing a *calling* Node Worker) is
different from killing the internal launcher; without its ownership closure,
host restart remains the conservative recovery. The old independent watchdog
Worker, whose crash formerly lost four/five handles per call, no longer exists.

## Single run and recovery deadlines (P1-B/P1-C)

The monotonic 15,000 ms execution deadline is recorded at the **first line of the
public entry, before shape screening and the complete P1A preflight**. The same
absolute value is passed into the session. Native loading, slot acquisition,
launcher initialization, repository/interpreter resolution, every probe,
calculation, transport and full output validation consume this budget. Probes
are additionally clamped to 5,000 ms, computation to 10,000 ms. Runner phase
requests carry their original monotonic request time; IPC delay consumes that
phase budget and execution requires a matching Host grant under that deadline.
No stage or interpreter candidate receives another total execution window.

The host owns an independent deadline timer **and** 10 ms polling loop. It awaits
no Worker message, Worker exit, launcher promise, provider done or watchdog
promise. Initialization that never returns and a launcher spinning synchronously
after restoring its runner cannot stop the host timer. Host takeover invokes
TerminateJobObject directly, then observes the whole Job and finalizes handles.
Promise.race and direct-child exit are not used as process-tree death proofs.

Only the trusted host assigns `cleanupEnd`, once:
`min(monotonicNow(), executionEnd, expiredPhaseEndWhenTimeout) + cleanupMs`,
where cleanupMs <= 3,000. A late timeout notification uses the already expired
phase deadline, so forwarding latency cannot grant a fresh three seconds.
Cancel, phase/total timeout, abnormal launcher exit, failed observation, catch
and finalization all reuse that value. There is no second cleanup window in
another component: the launcher does not initiate or time recovery. An explicit
operator recovery performs immediate queries/closes without another wait budget.
Cleanup deadline exhaustion returns REAP_FAILED and keeps BLOCKED until verified
recovery. The intended 15 + 3 second exit bound is scheduler-based, not a Windows
real-time guarantee. Late output/validation can never override a latched stop.

### Phase admission and dual enforcement (round 3 P1-A)

Observation-only phase messages allowed an accumulated Compute notification to
overwrite an expired Probe. The existing Host/Launcher/Runner processes now use
a private request/grant protocol over their existing pipes. No extra supervisor,
Job handle transfer, legacy Bridge change or DSH upgrade is introduced.

* Host creates a fresh random taskId. Ready is unique sequence zero. Subsequent
  phase, output, failure and finished frames have contiguous sequence numbers
  bound to this task. Missing, repeated, reordered and cross-task frames fail.
* Transitions are initial -> Resolve -> Probe -> Compute -> output; a completed
  failed Probe can return to Resolve for another candidate. Repeated Probe and
  transitions after Compute are rejected. TIMEOUT is never a retryable probe.
* Runner records requestedAt before requesting a phase and waits for its matching
  grant before creating/executing Python work. The deadline is always
  `min(executionEnd, requestedAt + phaseBudget)`, including time awaiting a grant.
* Launcher checks the PREVIOUS deadline before every transition/output, validates
  identity and order, arms that same candidate deadline BEFORE forwarding the
  request, and independently checks its monotonic timer. A delayed relay cannot
  start work because Runner has no grant. Local expiry stops Runner and reports
  TIMEOUT; only Host owns whole-Job reclamation and its sole recovery window.
* Host also checks the PREVIOUS deadline before every transition, output, failure
  and finish, then rejects an already expired candidate request. Host arms the
  original requestedAt-based deadline BEFORE sending a grant. Receipt time and
  a later Compute cannot create another Probe window. Full validation and final
  exit confirmation recheck the same deadline.
* Before authorization, Launcher/Runner enforce the pending request while Probe
  execution is prohibited. After authorization, Host independently knows the
  deadline and can kill the whole Job if Launcher stops scheduling. Thus no Probe
  executes under a deadline unknown to Host, even when forwarding is delayed.

Host grants are <=512 UTF-8 bytes through installed Koffi 3.1.1's async WriteFile,
with at most one outstanding call. Launcher-to-Runner grants may block only in
Launcher, after Host is armed. Timer callbacks recheck the monotonic clock to
avoid early expiry from millisecond rounding; `now >= deadline` is expired.
Already-established TIMEOUT cannot be undone by cancellation or late success;
unconfirmed cleanup instead requires REAP_FAILED/BLOCKED, without a second window.

Directed real-clock results: a 6,500 ms Probe relay with planned 5,250 ms Python
work returns TIMEOUT with NO Probe grant (6,780 ms); an independently authorized
5,250 ms Python sleep is cut off 5,002 ms after Probe request. Four 25x-shortened
cases (260 ms relay, 210 ms work, 200 ms budget) all TIMEOUT. Boundary cases at
deadline-100 ms / deadline / deadline+30 ms yield success / TIMEOUT / TIMEOUT.
No clock advancement is mocked. Actual prior-session replay and invalid phase
sequence/transition tests fail closed. A temporary bundle disables other timing
defenses to isolate Host's frame check; overdue Compute and output still TIMEOUT.

A non-settling callback fixture uses one 1.5 + 3 second test window, stays BLOCKED
with retained handles, then explicitly recovers with delta zero after settlement.
Normal protocol calls warm Koffi's process-lifetime async infrastructure first:
baseline 194, four repeats at 194. Before/after-resume crashes remain baseline
190, eight repeats each at 190. Neither sequence has per-call handle growth.

### Terminal cause and recovery status (round 6 initialization exception P2 repair)

The public entry installs one host-owned termination latch immediately after
recording its execution deadline, before preflight, native loading or slot
acquisition. The same latch is passed to Session and follows its admitted phase
deadline. Standalone Sessions install the identical latch before native loading.
Only observations on the existing monotonic clock establish order: if no cause
has been latched and now >= deadline, TIMEOUT wins, including initialization
with an already-aborted signal. The boolean signal carries no cancellation
timestamp and never proves that cancellation preceded expiry. An abort actually
observed and latched before the current deadline remains CANCELLED across slot
acquisition, Session initialization and recovery after expiry.

The first established execution failure is immutable. Later aborts, expiry,
duplicate termination events and late output/success cannot relabel it. Public
entry consumes a failed Session result before checking late caller state; the
same latch guards successful results. Abort listeners are removed on completion
and every public early return. Failed or throwing bounded slot acquisition also
checks the latch before returning a non-recovery admission error. Successful
acquisition still enters Session to confirm empty/closed state and release the
slot through the existing finalizer; an expired initialization creates no Job.

Real-clock initialization regressions cover four shortened Reviewer reproductions,
the original 15,000 ms budget, cancellation recorded before expiry, abort at
-15/-1/0/+1/+15 ms, bounded acquireSlot delays/false returns/errors, initialization
slot-release failure with BLOCKED/explicit recovery, and standalone aborted
signals with/without a trustworthy prior latch. No clock is advanced or
cancellation timestamp guessed. Existing runtime four-case reproductions and
recovery/handle/phase regressions remain required.

All Session stop paths observe that same latch/deadline before an ordinary
exception can establish a new cause. This includes errors returned by delayed
Job creation/configuration/readback, completion-port setup, pipe/handle setup,
CreateProcess, membership verification and ResumeThread. An ordinary error first
observed before expiry remains latched even if later cleanup crosses expiry;
an ordinary error first observed at/after expiry establishes TIMEOUT. Native
helpers retain their existing partial-cleanup closures and rethrow into this
shared path. Public preflight/native-admission catches already observe the latch;
public unexpected ownership failures and slot-release/recovery failures remain
fail-closed REAP_FAILED rather than ordinary admission errors.

During the synchronous initialization stack, an abort callback records its
trusted cause but cannot finalize resources whose ownership the initializer has
not yet returned. The normal initialization return/catch then runs the existing
tick/cleanup path with the exact owner/child/partial-cleanup state. This also
prevents a reentrant abort from falsely declaring an unreturned Job empty,
discarding a subsequent close failure, or leaving a timer armed after completion.
It adds no recovery window and does not alter the approved Host C boundary.

Round-6 bounded, disposable-copy regressions include four 100 ms createJob
reproductions, one unshortened 15,000 ms reproduction, nine exception-order
cases and twelve native-stage/cleanup fault cases. They verify Session/public
cause agreement, original-cause versus REAP_FAILED independence, BLOCKED and
explicit recovery, no owned/native handle growth, no abort-listener retention,
and safe failure envelopes. Earlier early/late cancellation and runtime
regressions remain in the full non-pressure suite.

Recovery safety is independent of the original cause. Termination/query errors
and rejected control writes mark recovery failure without overwriting
`latchedCause`. Incomplete Job reclamation, unclosed handles, recovery errors or
slot-release failure require public REAP_FAILED and BLOCKED; no engineering
results or lineage are returned. Explicit verified recovery remains mandatory.
A session can therefore retain TIMEOUT/CANCELLED as its internal original cause
while exposing REAP_FAILED for unsafe recovery. A slot-release failure occurs
after session completion and likewise blocks public admission. The original
single recovery deadline and handle ownership rules remain unchanged.

The round-4 regression supports `MECHANICAL_SUPERVISOR_SKIP_MEMORY_PRESSURE=1`
to explicitly skip all nine allocation-pressure scenarios. A run using it must
report those scenarios as unexecuted, never as passed. This repair does not
change the separately approved resource B and Host C boundaries below.

### Host synchronous work and control boundary

The host first rejects Proxy/accessor/custom-prototype data without executing
caller code. A fixed-schema gate rejects unexpected/deep subtrees before P1A's
generic snapshot; accepted input is bounded to 128 records and 16,384 envelope
bytes. Schema screening, preflight and bounded output parsing/validation are
synchronous; elapsed time is checked after each, and a slow completed operation
therefore returns TIMEOUT rather than obtaining another 15 seconds. Timers cannot
interrupt synchronous JS itself. Reflection on an arbitrarily huge already
allocated caller object, GC, a frozen host event loop or a hung kernel/native
call is **not an independently preemptible host operation**. No hard real-time
host-responsiveness claim is made for these cases. The user explicitly accepted
Host boundary C: the 15 second execution budget plus at most 3 seconds recovery
assumes a continuously responsive trusted Host, normal OS scheduling and native
calls that return. A synchronous Host deadlock has no hard real-time guarantee.

Interpreter/root filesystem access and all probes/computation execute in Job
processes and can be terminated by Host. Host makes no SYNCHRONOUS pipe WriteFile.
Full launcher/runner requests still travel in creation-time environment entries;
session control is removed before Python starts. Only small grants use the tracked
asynchronous writes described above.
Its reads PeekNamedPipe first, read at most 65,536 available bytes, and use a
single reader. Native waits and completion-port polls have zero timeout.
CreateProcess/Job/control calls remain synchronous Win32 calls; OS suspension,
driver/kernel hangs and arbitrary unrelated host code cannot be fixed by a
same-event-loop timer. A stronger guarantee against an arbitrary host stall
would require an independently scheduled host-lifetime controller; it is not
claimed or implemented in this repair.

The host validates the full P1A response and bit-exact request binding, requires
zero runner/launcher exit and complete framing, latches stop, terminates survivors,
queries zero active processes and confirms all local handle closures before any
success or slot reuse. Any cancellation/expiry during validation discards success.

## Resource configuration and memory measurement

Supported: Windows x64, Node >=24, functioning creation-time Job-list attributes,
nested Jobs, installed DSH Win32 0.2.0-rc.2 and Koffi 3.1.1. No weaker fallback.
Limits are set and read back before creation: KILL_ON_JOB_CLOSE, PROCESS_MEMORY,
JOB_MEMORY, ACTIVE_PROCESS; 268,435,456 process bytes, **536,870,912 Job bytes**,
16 active processes. The work Job includes launcher, runner, all ordinary Python
descendants and OS-associated helper processes. The unrelated DSH host is outside
this Job. Job Objects are process-tree resource governance, not a hostile
same-user sandbox against injection or service-mediated process creation.

Real allocation denial is exercised individually and in aggregate. Completion
port resource events latch RESOURCE_LIMIT, but ordinary notification delivery
is not guaranteed by Microsoft and enforcement does not depend on sampling.
The numeric caps have not been increased to hide measurement differences.

The `memory-counters` scenario queries the **explicit inner Job handle**, reads
its full PID list on every sample, opens each PID for K32GetProcessMemoryInfo and
sums PrivateUsage (offset 72, 80-byte x64 PROCESS_MEMORY_COUNTERS_EX). It records
PeakJobMemoryUsed (offset 136 in 144-byte extended limit information) separately.
Sampling sleeps 5 ms between sequential PID queries and therefore is neither an
atomic snapshot nor a proof of a maximum. This fixture contained eight associated
processes, with images **node.exe, python.exe and conhost.exe**; counting just the
explicit Node/Python processes misses associated console hosts. The outer Job is
independent and has a 1,073,741,824 byte limit; it is not the queried 512 MiB Job.

Recorded directed-repair run, bytes (three separate inner Jobs):

| Iteration | Configured Job limit | Kernel Job peak | Largest sampled PrivateUsage sum | Allocation denial |
| --- | ---: | ---: | ---: | --- |
| 0 | 536870912 | 538742784 | 533315584 | observed |
| 1 | 536870912 | 538816512 | 533049344 | observed |
| 2 | 536870912 | 540102656 | 533966848 | observed |

Microsoft defines PrivateUsage as per-process commit charge and continuously
tracks Job peak independently. Sampling time, missing/exited/helper processes
and Job hierarchy explain why the sampled sum cannot disprove a higher Job peak.
These measurements reproduce a peak above 512 MiB while configuration/readback
and allocation rejection work. They **do not establish the exact kernel cause**
of the over-limit peak (for example transient accounting versus live simultaneous
commit); no undocumented explanation is presented as fact. An absolute
PeakJobMemoryUsed <= 512 MiB guarantee is **unproved and excluded by approved B**. Configuration, denial behavior, observed peak and an
absolute instantaneous bound are four distinct claims. Under approved resource
contract B, the absolute instantaneous peak claim is no longer required.

### Historical option A investigation (superseded by approved B)

This records the earlier absolute-bound investigation; it is not the current
acceptance requirement after explicit user approval of B. No lower Job value or
substitute numeric peak threshold is deployed. Six contrasting bounded experiments keep
536870912 Job bytes, 268435456 process bytes and 16 processes. Three Python
allocators request 192 MiB each and retain successful allocations briefly;
commit quantum and serial/parallel admission vary. Each has its own outer Job
and confirms allocation denial and final emptiness. Experimental Node uses the
production --max-old-space-size=96 argument; Python limits are unchanged.

Windows 10.0.26200, 4096-byte pages, 65536-byte allocation granularity; eight
associated processes including the Node fixture, Python and console helpers.
The final full regression recorded six completed studies using that production
Node heap flag:

| Commit quantum | Admission | Job peak bytes | Excess over configured limit |
| ---: | --- | ---: | ---: |
| 1 MiB | parallel | 537726976 | 856064 |
| 8 MiB | parallel | 539742208 | 2871296 |
| 32 MiB | parallel | 556408832 | 19537920 |
| 1 MiB | serial | 537366528 | 495616 |
| 8 MiB | serial | 539475968 | 2605056 |
| 32 MiB | serial | 556552192 | 19681280 |

An observed historical ~5 MiB excess is therefore not a reserve bound, and
serial startup alone does not eliminate excess peaks. Page/allocation granularity
also does not establish a sufficient reserve. Full regression additionally
exposed the experiment's in-Job Node coordinator itself suffering OOM under
deliberate aggregate pressure, both before and after aligning with production's
Node heap flag. This is a real resource-denial failure path, not normal completion.
The experiment now explicitly records completedStudy/exitCode/coordinatorOOM:
either completed allocation statuses must contain DENIED, or a nonzero exit must
have BOTH a native resource-limit event and a known OOM exit/diagnostic. Unknown
failures still fail the test. Every path must confirm outer-Job emptiness.
Incomplete studies are not used as completed quantum/strategy measurements.
No Job/Python quota was relaxed and normal engineering capacity was not reduced.

A different native experiment holds two 192 MiB Python allocations and has a
third Python call VirtualAlloc(MEM_RESERVE | MEM_COMMIT) for 128 MiB:

* Before call: Job peak 459276288; caller PrivateUsage 10108928 bytes.
* VirtualAlloc returns NULL, GetLastError 1455; attempted bytes 134217728.
  Caller private usage plus the request fits below its unchanged 256 MiB limit.
* After denial: Job peak 593760256; caller PrivateUsage still 10108928 bytes.
  All limits read back unchanged and all processes are subsequently reaped.

The native experiment also requires an actual JOB_OBJECT_MSG_JOB_MEMORY_LIMIT
(10) in that explicit Job's completion queue, distinguishing its aggregate quota
pressure from the caller's process quota. Production enforcement does not depend
on event delivery; this is additional evidence in this bounded experiment.

This directly observes a rejected allocation coinciding with a large Job peak
increase and no lasting private allocation in its caller. It supports a
transient/precharge/rollback accounting explanation for the previous 517 MiB
observation, but does NOT prove the responsible kernel operation or exclude
temporary live system commit. A low PrivateUsage sample still cannot refute
PeakJobMemoryUsed. These differential measurements are not repeated identical
samples presented as worst-case proof.

A defensible conservative configuration needs a proven bound U for creation and
helper charges, concurrent allocator accounting and rejected-attempt peak updates
over supported OS/runtime/allocator paths. Only then could a Job configuration
at most `512 MiB - U` be justified, followed by full normal/max-input capacity
validation. Microsoft documents denial behavior and the peak field but provides
no overshoot/rollback bound usable for U. The process quota does not document
the ordering of attempted-allocation peak updates either. An arbitrary smaller
cap, sampled admission, or preallocating a reserve does not prove the missing
bound. No reliable option-A proof is available within the current scope.

### Approved resource contract B

The user explicitly approved the following resource boundary. This approval
does not declare P1B PASS; independent review and formal contract consistency
acceptance remain separate.

Effective resource guarantee:

1. Before any target resumes, set/read back JOB_MEMORY exactly 536870912,
   PROCESS_MEMORY exactly 268435456, ACTIVE_PROCESS 16, KILL_ON_JOB_CLOSE, with
   neither breakaway flag. Missing support or readback fails closed.
2. Require creation-time membership and inherited coverage of Launcher, Runner,
   ordinary Python descendants and associated helpers. DSH Host and its control
   infrastructure remain outside this engineering Job.
3. Rely on Windows Job committed-memory allocation denial under those exact
   quotas. Independently verify process and aggregate denial, including a native
   allocation that fits the caller's process quota but is denied under aggregate
   pressure (NULL plus kernel error). Events are diagnostic, not enforcement;
   unbounded successful allocation is an acceptance failure.
4. Record the exact PeakJobMemoryUsed and scope as independent diagnostics, and
   explicitly allow that statistic to exceed JobMemoryLimit. This is NOT an
   absolute instantaneous peak, RSS, total-system-commit or Host-memory bound.
   No substitute numeric peak allowance is invented. Existing termination,
   recovery deadline, handle closure and BLOCKED semantics remain mandatory.

Safety/stability effect: configured quotas, isolation and denial of sustained
successful growth remain; a strict instantaneous 512 MiB envelope is excluded from the approved contract. Large denied requests may record much higher peaks. Possible
transient system pressure, kernel behavior and memory outside the Job remain
risks; deployment needs separately accepted system headroom. This amendment
has explicit user approval; independent Reviewer acceptance of the implementation
remains required. It does not authorize the separate unapproved expansion B
(shared slots for the old three Native Tools), old Bridge/Tool changes, DSH
upgrades or another supervisor process.

## Transport, compatibility and verification

Python stdout/stderr limits remain 1 MiB / 16 KiB; runner framing 2,200,000 bytes;
host launcher framing 2,300,000 bytes. Bad UTF-8, incomplete/extra frames,
truncation, nonzero exit or binding mismatch fail closed. Public failures have
fixed safe messages, empty metadata, no results/lineage/raw diagnostics. The
host-fact environment allowlist excludes Node preload, Python search overrides
and credentials. Only fixed repository/Adapter selection is model-facing.

Build: `node packages/dsh-mechanical-plugin/scripts/build.mjs`.
Set an absolute installed MECHANICAL_AGENT_TEST_PYTHON, then run the complete
plugin suite or `node --test packages/dsh-mechanical-plugin/test/supervisor-windows.test.mjs`.
Each dedicated scenario has an independent outer Job: 1 GiB aggregate,
512 MiB per process, 32 processes, 25-second guard and 30-second test subprocess
timeout. Every scenario must print EXTERNAL_JOB_EMPTY after observing zero.
Faults patch only disposable temporary copies of built modules.

Directed scenarios cover before/after-resume launcher crashes (one warmup then
eight repeats each with GetProcessHandleCount and per-kind create/close ledger),
Job empty plus handle-close failure, launcher crash ~2.8 seconds into recovery,
permanent initialization, synchronous launcher spin after resume, takeover exactly
at validation (eight repeats), cancel/timeout/observation failure overlap,
BLOCKED admission rejection, failed and successful explicit recovery, no late
success/stale close/double close, total-budget preflight and all phase limits.
The repeated-crash directed run recorded 190 baseline and 190 after every repeat,
delta zero for both stages; each audit closed 54 pipes and nine each of Job,
port, process and thread handles (including warmup), with zero live ledger entries.

Full Python and plugin regressions, V1 Demo --verify against existing Golden,
the **actually mounted** old eleven-tool inventory, pinned DSH version and
git diff --check are required. Inventory uses the existing read-only probe while
headless waits on open stdin; it sends no model task and is terminated/observed
empty inside its own Job. No extra execution report, commit, push, tag or release
is produced. Independent Reviewer owns the final technical disposition.

Primary contracts:

* [Extended Job limits and peak fields](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information)
* [PrivateUsage / commit charge](https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-process_memory_counters_ex)
* [Nested Job accounting and termination](https://learn.microsoft.com/en-us/windows/win32/procthread/nested-jobs)
* [Creation-time Job-list and handle-list attributes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute)
* [Job inheritance, closure and notifications](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
