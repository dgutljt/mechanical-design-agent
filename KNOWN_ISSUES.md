# Known Issues

Status date: 2026-10-21 · Applies to: the v0.3.0 development source snapshot (experimental)

This is the consolidated known-issues list for the v0.3 experimental source snapshot. It complements the
[v0.3 source deployment scope](docs/V0_3_SOURCE_ONLY_DEPLOYMENT.md); where wording differs, that scope
document and the current gate decisions prevail. "Blocks formal runtime release" means: while the issue is
open, the project must not publish or claim a stable, fully accepted runtime release. Experimental source
snapshots may be published with these issues disclosed.

## KI-SAF-001 — Windows Supervisor security validation incomplete (C3/C4)

- **Status:** OPEN — blocking. C3 independent conclusion: **INSUFFICIENT EVIDENCE / BLOCKED**.
  C4 dynamic forensics has not run; C4-S0 (read-only forensics plan) is not independently accepted;
  VM work is paused.
- **Scope:** The bounded Windows Supervisor and Job-based process boundary of the explicit overhung
  workflow. `a1-lifecycle` expected `BREAKAWAY_DENIED` and observed `ESCAPED`; the runtime attribution
  of that observation is unresolved (it neither proves escape from the assigned Supervisor Job nor
  proves isolation held). Also covers the nine memory-pressure scenarios that the V1.5 safety policy
  forces to SKIPPED — skipped is not passed.
- **Blocks formal runtime release:** Yes.
- **Next review:** Independent Reviewer accepts the C4-S0 evidence specification and authorizes dynamic
  forensics under separate safety prerequisites; runtime attribution of the `a1-lifecycle` observation is
  determined; original failing assertions and acceptance criteria are kept unchanged.

## KI-NUM-002 — Old Native two-plane negative-zero path (P2)

- **Status:** OPEN — deferral conditionally accepted by the independent Reviewer (2026-10-21);
  the defect itself is **not fixed**; fix plan and schedule undetermined.
- **Scope:** The old numeric transport of the two-plane tool in the default 11-Tool profile. With an
  empty plane, Python produces `-0.0`, DSH rc.2 numeric/output validation rejects it, and the old Bridge
  returns `INTERNAL_ADAPTER_ERROR`. The path is proven fail-closed; there is no evidence of wrong
  engineering results being released. Other zero-weighted-sum cases may also trigger (static inference;
  the trigger scope must not be claimed to be limited to empty planes). The new overhung string transport
  preserves negative zero and is not subject to this path; a DSH-equivalent workaround is UNVERIFIED.
  Deferral conditions: do not alter payloads, do not substitute the overhung model, and do not rewrite
  negative zero as an accepted solution; keep fail-closed behavior; disclose as a known issue in
  experimental releases.
- **Blocks formal runtime release:** Yes, until fixed and re-verified.
- **Next review:** Any fix keeps fail-closed behavior and the original acceptance criteria, re-runs the
  affected regression, and is accepted by the independent Reviewer before the deferral is closed.

## KI-DEP-003 — No complete packaged deployment (wheel/sdist gaps)

- **Status:** OPEN.
- **Scope:** wheel and sdist do not include `knowledge/` model cards and source registry, and the wheel
  also lacks the root `pyproject.toml` that the version probe requires. The Registry resolves `knowledge/`
  from the source tree, so a packaged install cannot run the full Adapter (fail-closed `REVIEW_FAIL`).
  The plugin is `private: true` with no independent npm delivery acceptance. The only supported
  deployment form is a full source checkout with a local editable install and a local plugin build.
- **Blocks formal runtime release:** Yes — a formal release needs a defined, verified installation path.
- **Next review:** Packaging of the `knowledge/` data and the version probe is designed and verified, or
  the source-only deployment form is formally accepted as the product delivery form.

## KI-COMP-004 — Fresh-machine and compatibility verification insufficient

- **Status:** OPEN.
- **Scope:** C2 verified source deployment only under pre-existing trusted local dependencies
  (Junction-linked caches; not a clean dependency download). There is no complete npm lockfile.
  The declared Python >=3.12 / Node >=24 ranges, Windows 10 / other builds and editions / Windows
  Server / ARM64, non-Windows platforms, the LF/CRLF matrix, cache-Junction permission portability,
  and full rollback deployment are UNVERIFIED. Observed environments: Windows 11 x64 (10.0.26200)
  with Node 24.18.0; C2 venv Python 3.12.14; the earlier reproduction used Python 3.14.6.
- **Blocks formal runtime release:** Yes.
- **Next review:** A fresh-machine install with clean dependency acquisition, or an explicit decision to
  narrow the supported platform matrix, accepted by the independent Reviewer.

## Dependency and ecosystem watch policy

Before each future minor release, check for changes in GitHub, the pinned DSH / DSH Tools / Win32 process
provider (currently 0.2.0-rc.2), Python, Windows, and related plugin dependencies, and record the findings
in the release notes. This watch does not upgrade any dependency automatically; any upgrade requires
separate authorization and re-verification.
