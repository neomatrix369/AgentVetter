# Capability status

Evidence-labelled claims for AgentVetter.

Start here: [QUICKSTART](../QUICKSTART.md) · Hub: [docs/README](./README.md) · Repo: [README.md](../README.md)

### Evidence-state legend

| Label | Meaning |
|---|---|
| **RESEARCH** | Investigated; no delivery commitment |
| **PROPOSED** | Candidate awaiting approval |
| **DECIDED** | Approved direction; may not exist in code yet |
| **IMPLEMENTED** | Reachable through a production entry point or config |
| **VERIFIED** | Observed with a dated command, test, probe, or runtime result |
| **SUPERSEDED** | Replaced by newer evidence or decision |

RESEARCH · PROPOSED · DECIDED · IMPLEMENTED · VERIFIED · SUPERSEDED.

[![Cursor](https://img.shields.io/badge/Cursor-000000?style=flat)](https://cursor.com)
[![Modal](https://img.shields.io/badge/Modal-7C5CFF?style=flat)](https://modal.com)
[![Supabase](https://img.shields.io/badge/Supabase-3ECF8E?style=flat&logo=supabase&logoColor=white)](https://supabase.com)
[![AgentVetter](https://img.shields.io/badge/AgentVetter-1a1a2e?style=flat)](https://github.com/neomatrix369/AgentVetter)

[![Cisco](https://img.shields.io/badge/Cisco-1BA0D7?style=flat)](https://developer.cisco.com)
[![Snyk](https://img.shields.io/badge/Snyk-4C4A73?style=flat&logo=snyk&logoColor=white)](https://snyk.io)
[![Tessl](https://img.shields.io/badge/Tessl-111111?style=flat)](https://tessl.io)
[![DepShield](https://img.shields.io/badge/DepShield-2F6F4E?style=flat)](https://www.npmjs.com/package/depshield-mcp)
[![Ossprey](https://img.shields.io/badge/Ossprey-1A1A2E?style=flat)](https://ossprey.com)
[![Superlinked SIE](https://img.shields.io/badge/Superlinked%20SIE-0B1F3A?style=flat)](https://superlinked.com)
[![Alibaba Cloud Model Studio](https://img.shields.io/badge/Alibaba%20Cloud%20Model%20Studio-FF6A00?style=flat)](https://www.alibabacloud.com/product/modelstudio)

---

## IMPLEMENTED

Reachable through production entry points / config:

- Full schema + rollup function + anon SELECT policies/GRANTs + Realtime
  publication on `scan_runs` / `scan_run_scanners` / `findings` — `db/schema.sql`,
  applied via `agentvetter setup` / `cli/src/ensureSchema.js`
- `scan_run_scanners` incremental writes from Modal (`running` placeholders,
  `console_output`, `started_at`/`completed_at`; PGRST204-safe fallback when
  columns missing) — `sandbox/`
- CLI discovery / hashing / idempotency / batching — `cli/` (`agentvetter scan`)
- CLI scanner inventory after scan (per-source status + rollup
  `fully successful` / `partly successful` / `fully failed` / `not run`;
  zero-artifact paths list registry as `not_run`) — `cli/src/scannerInventory.js`
  (slice 63 ✅ on `main` via #145/#146). Package expected sources include
  **Cargo Audit** (RustSec) alongside Snyk / DepShield / Ossprey.
- Language/ecosystem **coverage ledger** (slice 65, Wave R): `agentvetter scan`
  / `--dry-discover` prints `[coverage]` rows per discovered ecosystem
  (volume, scanner, action status, unsupported portions, reason) —
  `cli/src/coverageLedger.js`. Marker-driven discovery (not a closed language
  list). Snyk/`snyk test` + DepShield still do **not** cover Rust/Cargo — that
  gap stays explicit; RustSec **Cargo Audit** covers `Cargo.lock` / `Cargo.toml`
  when installed (slice 72 formalizes that path). Rollup is never “fully
  successful” solely from empty findings.
  Local approved checkouts with manifests also emit a `package` target.
  Cargo SCA honesty from `fix/cargo-package-scan-error-status` (#147) is
  absorbed — no parallel Cargo-detail path.
- Host-side **evidence verify + injection guard** (slice 66, Wave R): quoted
  findings are `evidence_verified` only when the text exists at the reported
  path:line; mismatches fail closed and are never independently confirmed.
  Deterministic guards record hidden/encoded instruction attempts; scanned
  content is wrapped as `untrusted_data` (never system/judge instructions).
  Secret-like tokens are masked in logs/prompts unless `--reveal-secrets`.
  `agentvetter scan` / `--dry-discover` print `[evidence]` rows —
  `cli/src/evidenceVerify.js`. IMPLEMENTED (host/CLI); finding-row persistence
  stays slice 67.
- Wave R **workflow stepper** Run→Triage→Investigate (slice 68): IMPLEMENTED /
  VERIFIED on `main` (#152) — `prototypes/dc-dashboard/agentvetter-workflow-*.js`
  (+ run-progress / triage / investigate) with GWT-68.* tests. **Nav (2026-09-20):**
  primary **Dashboard** tab = inventory (default); stepper + phase panels move to
  secondary **Workflow** tab — IMPLEMENTED on `main`
  ([#160](https://github.com/neomatrix369/AgentVetter/pull/160)).
- Wave R **Triage target filters** (slice 73): ✅ PASSED — merged-on-main;
  formal close 2026-09-20 (Gate 4 APPROVED). Triage panel adds inventory-style
  type tabs (All / Skills / MCP / Packages), quality tabs (All + Tessl
  high/low/unscored), and per-target chips; filters compose with status tabs;
  finding rows show target name. SCA triage titles prefer `package@version · CVE`
  (not bare `dependency_vulnerability`); Live maps `package_name` /
  `package_version` / `cve_ids`. Module: `agentvetter-triage.js` + Triage panel in
  `AgentVetter.dc.html`; GWT-73.* tests.
- Wave R **workflow model labels** (slice 74): ✅ PASSED (formal close 2026-09-20)
  — IMPLEMENTED / VERIFIED. Stepper tabs show role-aware default model aliases
  for stages that use models (Run panel light/mid + final stronger; Triage SIE;
  Investigate SIE/MS; Fix blank while propose is heuristic). Soft-amend
  (2026-09-20): role labels, Fix empty while heuristic-only, per-target
  type·name on model lines. Module: `agentvetter-workflow-models.js`; GWT-74.1–74.5;
  Gate 4 APPROVED.
- Wave R **Fix propose + apply-clean** (slice 69): IMPLEMENTED / VERIFIED on
  `main` (#154) — proposed unified diff, root-cause vs quick-patch label,
  apply-clean on a temp copy only (approved repo unchanged), mark fixed /
  won't-fix (reason required), J/K navigation, progress N of M. Never claims
  fixed from generation alone — Verify (slice 70) owns outcomes.
- Wave R **Verify worktree rescan** (slice 70): IMPLEMENTED / VERIFIED on
  `main` (#155) — Verify step honesty: outcomes are
  **finding gone** / **still present** / **unable to verify** (with reason);
  re-check runs only on a temp worktree/copy (approved repo unchanged);
  scanner missing/failed/timeout → unable, never “finding gone”; never claim
  fixed solely because a patch was generated (slice 69). Modules:
  `agentvetter-verify-rescan.js`, `agentvetter-verify-view.js` (dashboard prototype).
- Wave R **Expert view + Report export** (slice 71): IMPLEMENTED / VERIFIED on
  `main` (#153) — on the **Workflow** tab, Expert toggle surfaces raw judges,
  model IDs, confidence, weakness/AI-sec IDs, scanner details, data-flow (Simple
  remains the default density); Report step headline (fixed / left / won't fix)
  with JSON/Markdown export + coverage ledger; secrets masked unless Reveal
  secrets. Modules: `agentvetter-report.js`, `agentvetter-report-export.js`; GWT-71.*
  tests. Expert no longer gates the inventory grid (that is the Dashboard tab).
- Wave R **operator-visible pipeline** (slice 75 / R-UX-1): IMPLEMENTED /
  VERIFIED (unit) on `main` ([#163](https://github.com/neomatrix369/AgentVetter/pull/163)) —
  Workflow UI narrates judge-panel / coverage / evidence-verify with honest
  absent states (no fabricated pending judges; process line + primary CTA;
  Investigate auto-select / final-judge lines; Fix does not inject false
  `gen-27b`); L→R soft-amend **IMPLEMENTED** (GWT-75.9–75.11: parent type·name
  on findings, keyboard multi-select + `k of N` progress, role-labelled /
  parent-attributed model lines). Modules: `agentvetter-workflow-pipeline.js`,
  `agentvetter-workflow-models.js` (+ Run/Triage/Investigate/Fix HTML wiring);
  GWT-75.1–75.11 unit green; Gate 4 APPROVED on landing branch. Spec:
  [plan/slices/18-R-approved-repo-workflow/slice-75-operator-visible-pipeline.md](./plan/slices/18-R-approved-repo-workflow/slice-75-operator-visible-pipeline.md).
- Wave R **Workflow chrome polish** (slice 76): ✅ PASSED on `main`
  ([#165](https://github.com/neomatrix369/AgentVetter/pull/165)) — IMPLEMENTED /
  unit-VERIFIED. Shared `tw-panel-*` typography (kicker / title / meta / body)
  across Run→Report; compact Triage `tw-filter-toolbar` rows with
  Type/Quality/Target/Status labels; plain-language override buttons. Filter
  semantics unchanged. Spec:
  [plan/slices/18-R-approved-repo-workflow/slice-76-workflow-chrome-polish.md](./plan/slices/18-R-approved-repo-workflow/slice-76-workflow-chrome-polish.md).
- Wave R **Workflow smoke fixes + target-scoped Fix→Verify** (slice 77):
  IMPLEMENTED / VERIFIED (unit GWT-77.* + Mock/Live browser smoke 2026-09-21)
  on branch `slice/77-workflow-smoke-fix-target-flow` (not yet on `main`) —
  Run CTA unlocks for terminal `not_applicable`/`blocked`; process line matches
  active scanner rows; Triage/Fix/Report share one deduped universe; triage
  disposition buttons persist via idempotent `stableFindingId`; target focus +
  single-select; Verify honesty before/after Mark fixed. Spec:
  [plan/slices/18-R-approved-repo-workflow/slice-77-workflow-smoke-fix-target-flow.md](./plan/slices/18-R-approved-repo-workflow/slice-77-workflow-smoke-fix-target-flow.md).
- CLI **`agentvetter judge --batch-id`** + SIE judge panel module (slice 67, Wave R):
  `cli/src/judgePanel.js` (panel + final judge; open-weight SIE generate models).
  Optional soft-fail post-route hook only when `AGENTVETTER_JUDGE_PANEL=1` (default
  off — ADR-0016 auto-route unchanged). Unit tests: `cli/test/judgePanel.test.js`.
  IMPLEMENTED (CLI + unit); Live/gate VERIFIED pending.
- Git repo `package` discovery target (`items.type=package` when manifests at
  scope root; DepShield / Ossprey / Snyk / Cargo Audit) — `cli/src/discovery.js`,
  `sandbox/scanners.py` `_group_applies` (slice 64 ✅ on `main` via #145/#146;
  Cargo-only SCA honesty VERIFIED on Live — all-N/A → NO COVERAGE, not green)
- `agentvetter setup` / first-scan schema bootstrap (probes `completed_at` column and
  live `items_type_check` so pre-package DBs re-apply `db/schema.sql`) —
  `cli/src/ensureSchema.js`
- `./scripts/setup-modal.sh` secret sync + deploy
- Scanner adapters shell out to upstream CLIs (`skill-scanner`, `mcp-scanner`,
  `snyk-agent-scan` for skills/MCP, `snyk test` SCA for `package`, `tessl`) with
  real flags and parse documented output shapes — `sandbox/scanners.py`. Package
  Snyk: Rust/Cargo trees → `not_applicable` (no `snyk test` support); complete
  runs with zero completed engines → rollup/dashboard **grey** (NO COVERAGE)
- **Cargo Audit** (RustSec `cargo-audit`) SCA adapter — `Cargo.lock` /
  `Cargo.toml` trees; registered in `SCANNER_GROUPS` between DepShield and
  Ossprey; Modal image installs `cargo-audit` when possible. **IMPLEMENTED** on
  `main` (production path via `run_cargo_audit` / `_run_cargo_audit_group`).
  Slice 72 formalizes this as the Rust/Cargo gap scanner. Absent binary →
  unreachable/skipped honesty — do not claim VERIFIED Live unless citing a
  dated Live run. Prefer RustSec over LLM Rust analysis (LLM deferred).
- DepShield dependency-audit adapter (`depshield-mcp` over MCP stdio;
  npm + PyPI via OSV.dev; zero credentials — nothing synced to
  `agentvetter-scan-secrets`; runs for skill, mcp_server, and package
  (`applies_to: both`), before Cargo Audit / Ossprey in the
  `SCANNER_GROUPS` registry) — `sandbox/scanners.py`, unit-tested in
  `sandbox/tests/`. IMPLEMENTED only: no live-Modal run recorded yet, so no
  VERIFIED (operator) claim — see
  [scanner-output-adapters.md](./research/adapters/scanner-output-adapters.md) §7
- Ossprey malware / malicious-package adapter (`ossprey-cli`, [ossprey.com](https://ossprey.com);
  credential-gated `OSSPREY_API_KEY`; registered **after** Cargo Audit in
  `SCANNER_GROUPS`; skill, mcp_server, and package). Absent key → `skipped_missing_credential`.
  IMPLEMENTED (adapter reachable) + RESEARCH (vendor-docs parsing, not live-probed);
  access provisioning still OPEN (slice 35 🔴) — no VERIFIED live claim.
  Public README listing allowed per DECISIONS `ossprey-readme` (2026-08-25).
  See [scanner-output-adapters.md](./research/adapters/scanner-output-adapters.md) §8 ·
  [OPTIONAL_SCANNER_KEYS](../fixtures/OPTIONAL_SCANNER_KEYS.md)
- Fixture set under `fixtures/` — see [fixtures/README.md](../fixtures/README.md)
- `_acquire_target` dispatch (git clone, local copy, host→sandbox tar upload via
  `local_entrypoint`, MCP introspection-only empty workdir) — `sandbox/`
- Dashboard Live/Mock with Supabase Realtime (~1s) + 8s poll fallback, SCANNING
  in-flight UI, scanner console / raw output in drawer, collapsible Findings
  heading (rotating chevron; **collapsed by default**) plus Modal console and
  Raw output collapsed until expanded, partial-failed “n out of m scanners
  unreachable” copy — `prototypes/dc-dashboard/`;
  `scripts/serve-dashboard.mjs` / `scripts/sync-dashboard-config.sh`
- Dashboard visual identity v2 (FolderGate cream/tan × AgentVetter HUD): paper
  `#F5F2EA`, tan CTA `#C4A574`, Fraunces on intro `h1`/`h2`, AA ink tokens,
  cyan as live signal only; partial-scan / Guard banners use violet/status ink
  (not dark-theme pastels) — `prototypes/dc-dashboard/AgentVetter.dc.html`,
  `agentvetter-status.js` (slice 43 ✅, [PR #96](https://github.com/neomatrix369/AgentVetter/pull/96);
  alert-ink pile-on on slice 42 branch). Screenshot gallery regenerated 2026-08-20
- Landing intro screen (threat stats, SEC/01–05 sections, sessionStorage
  `agentvetter-intro-dismissed`, About toggle) — `prototypes/dc-dashboard/AgentVetter.dc.html`
  (slice 41 ✅)
- Tessl `quality_score` (0–100 skill-review) persisted on `items`, mapped by Live
  to `item.quality` / `"Tessl: Review (Quality)"` `output.quality_score`, and surfaced on skill cards as
  compact `Q N` / `Q —` / `Q ?` badges with fixed `#score-tip-portal` hover/focus
  tips + schedule cues — `sandbox/scanners.py`, `agentvetter-live.js`,
  `agentvetter-status.js`, `AgentVetter.dc.html` (slice 42 A9–A13 ✅,
  [PR #98](https://github.com/neomatrix369/AgentVetter/pull/98); quality binding
  scoped off `"Tessl: Lint"` in slice 46)
- Dashboard quality triage tabs — **Quality ≥ 80**, **Quality < 80**, and
  **No quality score** skill-only filters on Tessl `item.quality` (80 threshold),
  tab counts, empty-state copy, and clear-filters reset — `agentvetter-status.js`,
  `AgentVetter.dc.html` (slice 42 A14–A15 IMPLEMENTED)
- `"Tessl: Lint"` scanner row — `run_tessl()` invokes `npx tessl@latest skill lint`
  first (auth-free, no `tessl_run_id`); Review row is `"Tessl: Review (Quality)"`
  and Review `needs_setup` when `TESSL_TOKEN` or `TESSL_WORKSPACE` is absent
  (Lint still runs). Mock dashboard fixtures include
  Lint at Tessl-block position 1. Live CLI 2026-08-24: lint targets plugin
  packages; skill-folder fixtures exit 1 (adapter → `failed`). IMPLEMENTED +
  VERIFIED(unit) + VERIFIED(live persist scan_run `a36cad9f`, 2026-08-24) —
  `sandbox/scanners.py`, `prototypes/dc-dashboard/` (slice 46 ✅,
  [PR #105](https://github.com/neomatrix369/AgentVetter/pull/105))
- `"Tessl: Review (Quality)"` run-ID capture — `_run_tessl_review(judge_type="quality")`
  invokes `tessl review run quality --json --workspace` (deprecated `skill review`
  replaced) then `tessl review view --last --json` to persist `tessl_run_id` +
  `tessl_run_id_at`. `_update_tessl_id_context` seeds `ctx["review_quality"]`
  in-process (GWT-47.5). Missing `TESSL_WORKSPACE` → `needs_setup`. IMPLEMENTED (unit)
  — `sandbox/scanners.py` (slice 47 ✅,
  [PR #109](https://github.com/neomatrix369/AgentVetter/pull/109); GWT-47.1–47.5)
- Dashboard Tessl "Not Available Yet" placeholders — Scanner Outputs always shows
  five Tessl capability rows when any Tessl DB row exists; missing sources among
  Scenario Generation / Eval / Review (Security) are UI-only sentinels
  (`status: not_available_yet`) when absent from the scan_run (never stored as
  placeholders) and counted in the header. Runners 49–51 write Scenario Gen,
  Eval, and Security rows when they run; missing Tessl sources stay NAY. MCP scans
  unchanged. IMPLEMENTED (unit) +
  VERIFIED (Mock UI 2026-08-24: `safe-changelog-writer` Scanner Outputs (7),
  five Tessl rows, three NAY pills, no chevron; MCP `SCANNER OUTPUTS (3)`
  unpadded) — `agentvetter-status.js` `mergeTesslCapabilityRows`, `AgentVetter.dc.html`
  (slice 48 ✅
  [PR #110](https://github.com/neomatrix369/AgentVetter/pull/110); formal close
  2026-09-21 packing Gate 4 APPROVED). Security Review writes a real DB row from slice 51 (NAY only when
  that source is still absent).
- Tessl Scenario Generation — `run_tessl()` emits `"Tessl: Scenario Generation"`
  after Review (Quality): plugin-path `scenario generate --count 3`, download to
  `<plugin>/evals/`, `upstream_run_ids.review_quality` from ctx, `tessl_run_id`
  stamp, `resume_checkpoint` + mid-scan persist via `on_scanner_progress`.
  Missing token → `needs_setup`; missing `.tessl-plugin/plugin.json` → `failed`.
  IMPLEMENTED (unit) — `sandbox/scanners.py` / `sandbox/scan_app.py` (slice 49 ✅ #112)
- Tessl dashboard mid-scan progress — `on_scanner_start` no longer bulk-inserts
  all five Tessl sources as `running`; `run_tessl()` emits per-step progress for
  Lint and Review (Quality) via `on_scanner_progress` (Scenario/Eval/Security
  already did). Fixes frozen-all-Running appearance during Modal scans.
  IMPLEMENTED — `sandbox/scanners.py` / `sandbox/scan_app.py` / `agentvetter-status.js`
- Tessl Eval auto-chain — `run_tessl()` emits `"Tessl: Eval"` as `blocked` before
  Scenario Generation, then auto-chains to `queued`→`running` when generation
  completes and `<plugin>/evals/` has scenarios; `tessl eval run --runs 3 -y
  --json` + `eval view` poll; `upstream_run_ids` from ctx; project create/repair
  preflight; scenario re-run marks prior completed Eval `stale` (no cascade).
  IMPLEMENTED (unit) — `sandbox/scanners.py` / `sandbox/scan_app.py` (slice 50 ✅ #113)
- Tessl Review (Security) — `run_tessl()` emits `"Tessl: Review (Security)"` after
  Eval using `_run_tessl_review(judge_type="security")` (`tessl review run security
  --json --workspace`); `upstream_run_ids.review_quality` from ctx before invoke;
  Security `tessl_run_id` via `review view --last --json`. Dashboard expanded
  Security row shows linked Quality findings when that ID is populated (UI-level,
  no live Tessl fetch — slice 52). IMPLEMENTED (unit) —
  `sandbox/scanners.py` / `agentvetter-status.js` (slice 51 🔀)
- Live dashboard latest-state read path — `dashboard_latest_runs` view (one row per
  item) + batched child-table fetches in `agentvetter-live.js`; replaces global
  `scan_runs?limit=2000` page that could miss per-item newest runs and PostgREST
  single-response truncation on large fleets. IMPLEMENTED (unit); operator applies
  view via `agentvetter setup --force`. Partial slice 21 — 🔀 `fix/dashboard-latest-runs`
- `risk_score` weighted finding density from `agentvetter_rollup_item`; cards show
  compact `R N.NN` badges with density-formula portal tips (list header **Risk density**);
  card colour remains worst-of `heatmap_status`, not density (slice 42 A11/A13)
- Tiered post-scan router (SIE triage + optional Model Studio escalation) —
  `agentvetter route`, auto-route after `agentvetter scan`
  (`cli/src/router.js`, `cli/src/orchestrator.js`); dashboard router strip +
  SIE-only / escalated filters — `prototypes/dc-dashboard/`; sample CLIs —
  `prototypes/sie-studio/`, `prototypes/model-studio/` ([ADR-0016](./adr/0016-tiered-router-sie-model-studio.md))

---

## VERIFIED (unit)

- `cd cli && npm test` — discovery, content-hash, schema-probe (incl. `completed_at`),
  `--force`, tiered router (`cli/test/router.test.js`)
- `pytest sandbox/tests/test_acquire_target.py` — acquire-target dispatch
- `cd prototypes/dc-dashboard && npm test` — Live gating, Realtime wiring,
  SCANNING/console/unreachable mapping; Tessl Lint vs Review (Quality) inner
  quality scope (GWT-46.4); Tessl NAY sentinels (GWT-48.1–48.4) — 100 pass /
  0 skip excluding optional live-smoke (2026-08-24); live-smoke reads
  repo `.env`

---

## VERIFIED (operator, 2026-08-01)

- Modal secrets + `agentvetter-scan` deploy with `scanners` packaged
  (`add_local_python_source(..., copy=True)`)
- Host tar packing (`modal run sandbox/scan_app.py` → `[acquire] packed …`)
  delivers fixture `SKILL.md` to scanners — Cisco completed with findings
  (incl. red prompt_injection); Tessl/Snyk may still be unreachable
  (Node≥20 / `uvx` cold-install)
- Live dashboard reads items when anon key synced (or via local proxy)
- Live `agentvetter setup` against Direct `db.*` host was **not** verified here
  (`ENOTFOUND`); use Session pooler URI when needed

---

## VERIFIED (coverage gates) · ON BRANCH (documentation sync)

Ship-path coverage uplift (~95% instrumented on `cli/src`, `sandbox/`, Live ACL JS;
omit `guard/` and `support.js`) is verified: slice 11 ✅, 12 ✅, 13 ✅ (CLI and
live bars from `plan/gate-evidence/slice-12.json` / `slice-13.json`; slice 11
status via `slice-11` evidence). audit matrix ✅ (slice 7); onboarding Phase 1 ✅
(17); Wave K public docs UX (slice 44) on branch — Setup vs Configure framing,
services inventory + journey/dependency diagrams;
skill parse ✅ (8). The coverage gates are verified; their final documentation
sync (slice 14) is on branch and awaits merge. Groups:
[plan/PROGRESS.md](./plan/PROGRESS.md),
[plan/DECISIONS.md](./plan/DECISIONS.md), [plan/GATE_CONTRACT.md](./plan/GATE_CONTRACT.md).

Measured ship-path floors are: Python `sandbox/` **95.91%**; Live ACL
**98.48%** lines. CLI coverage floors are temporarily **60%** lines/functions/
statements and **80%** branches in `cli/package.json` while overall CLI
instrumented coverage is still climbing back toward the ADR-0013 ≥95% target
after the router land. Unit coverage for the router **does** exist:
[`cli/test/router.test.js`](../cli/test/router.test.js). Temporary floors are a
gate-policy choice, not “missing tests.” [ADR-0013](./adr/0013-ship-path-quality-gates.md)
still records the intended ≥95% CLI ship-path target. T4 cloud is split
(**USER-CONFIRMED** 2026-09-09; **A** expanded 2026-09-11): **A** Nightly
comprehensive T4 **daily 02:00 UTC** (Semgrep · CodeQL · full scans · dashboard
tests · cov snapshots); **B** Supply chain **weekly Mon 03:00 UTC**; **C**
Mutation **1st+15th 04:00 UTC** (Stryker/mutmut **non-gating**). PR CI is
ultra-minimal (ship-path coverage + OSV + targeted scans). See
[ADR-0013](./adr/0013-ship-path-quality-gates.md) and CONTRIBUTING.
Exact gate matrix:
[plan/coverage-audit.md](./plan/coverage-audit.md).

Heatmap note: card `heatmap_status` is **worst-of** actionable scanner findings
(any red → red; amber-only → amber) when ≥1 scanner **completed**; finding-count
chips are density, not colour. A `complete` run with **zero** completed engines
(all `not_applicable` / skipped — e.g. Cargo-only packages) → **`grey`
(UNSCANNED)** with `risk_score` null, not green / `R 0.00`. Router rows
(`tiered_router`) are excluded from severity rollup.
`risk_score` = `(3×red + 1×amber) / Σ completed checks_run` (unbounded ≥0) for
sort/trend only — see [ARCHITECTURE.md](./ARCHITECTURE.md) § Quality attributes.

---

## ON BRANCH (awaiting merge)

Wave K — Docs UX plain language + compaction (slice 44) on
`slice/44-docs-ux-plain-language` ([PR #99](https://github.com/neomatrix369/AgentVetter/pull/99)):
GWT-44.1–44.4 compaction plus pile-ons GWT-44.5–44.8 (Setup vs Configure beats,
MVP Live, Maintain hub, screenshots `R`/`Q`, ARCHITECTURE External services
inventory + operator journey + dependency-order Mermaid). Documentarist pile-on
**APPROVED WITH FOLLOW-ON** (2026-08-21): QUICKSTART / docs hub / screenshots
APPROVED; pre-existing DIVIO rewrites for `env-vars` procurement table and
`prerequisites` capability bullets are **DECIDED** (same-branch content commit;
merge not held; targets still pending). Gate evidence
`docs/plan/gate-evidence/slice-44.json` (`gate_status: ON_BRANCH`,
`commit_at_evidence: 0362d36`).

Live Modal/Supabase E2E as a CI Must remains **Won't** for this wave (slow/optional
skip-without-config stays). Demo/hackathon film day (VO/Remotion slice 4; film-day
prose slice 16) is **Won't (A)** — reinstate only if a new demo need arises.

---

## DECIDED

Architecture boundaries and quality/security trade-offs are recorded as formal
ADRs ([adr/README.md](./adr/README.md)): runtimes (0002), Modal (0003),
Supabase (0004), scanner adapters (0005), Live/Mock ACL (0006), ship UI (0007),
anon-read / service-role-write (0008), fail-closed evidence (0009), content-hash
idempotency (0010), schema bootstrap (0011), target acquisition (0012),
ship-path quality gates (0013), curated discovery (0014), Horizon A
excluding Guard/Drift (0015), and tiered SIE/Model Studio router (0016). Slice
waivers stay in [plan/DECISIONS.md](./plan/DECISIONS.md). [ADR-0001](./adr/0001-monk-deployment-and-packaging.md)
(**Proposed**) records the intended Monk Kit Live packaging path — **not
IMPLEMENTED** and **not VERIFIED**. The supported Live path remains the
operator workstation flow (local `.env`, CLI, QUICKSTART). Implementation
slices are Wave **15-O** (**O0** + 58–61) under
[plan/TRAIL.md](./plan/TRAIL.md) — plan-only until explicitly executed.

**Wave R — Approved-repo security workflow (2026-09-20):** Slices **65–72**
landed/verified on `main` (Must **65–69**, Should **70–71**, Could **72**).
Slice **67** SIE judge panel CLI + module on `main` (#151): model inventory
`gen-4b` / `gen-27b`; fewer than 3 models → parallel same-model executions;
opt-in `AGENTVETTER_JUDGE_PANEL=1` (default off). Panel is **additive** to
[ADR-0016](./adr/0016-tiered-router-sie-model-studio.md). Should **73–76** Workflow UI (triage filters, model labels, operator-visible
pipeline / R-UX-1, chrome polish) **IMPLEMENTED / VERIFIED** (unit) on `main` —
**75** via [#163](https://github.com/neomatrix369/AgentVetter/pull/163); **76** via
[#165](https://github.com/neomatrix369/AgentVetter/pull/165). See
[plan/DECISIONS.md](./plan/DECISIONS.md).

**Wave J delta — dashboard metric surfacing (2026-08-20):** A9–A13
**IMPLEMENTED** on `main` via [PR #98](https://github.com/neomatrix369/AgentVetter/pull/98)
(nw-review APPROVED). Spec:
[plan/slices/10-J-dashboard-data-quality/slice-42-dashboard-data-quality-fixes.md](./plan/slices/10-J-dashboard-data-quality/slice-42-dashboard-data-quality-fixes.md).

**Wave J delta — quality triage tabs (2026-08-25):** A14–A15 **IMPLEMENTED**
on `slice/42-quality-score-tabs` — three skill-only toolbar tabs filter by Tessl
`item.quality` (≥80 / <80 / unscored). Awaiting PR + nw-review before ✅ PASSED.

**Wave K — docs UX (2026-08-20/21):** Slice 44 compaction, Setup/Configure framing,
and services/diagrams pile-ons are **IMPLEMENTED** on branch (public docs);
documentarist pile-on **APPROVED WITH FOLLOW-ON**; DIVIO purity rewrites
(env-vars / prerequisites) remain **DECIDED** pending content commit — see
[ON BRANCH](#on-branch-awaiting-merge). Spec:
[plan/slices/11-K-docs-ux-plain-language/slice-44-docs-ux-plain-language.md](./plan/slices/11-K-docs-ux-plain-language/slice-44-docs-ux-plain-language.md).

**Wave H — Frontline agent hooks (2026-08-15):** **H0 governance ✅**
(2026-09-21 — [phase-H0-governance](./plan/slices/08-H-frontline-agent-hooks/phase-H0-governance.md)).
Claude Code PreToolUse handlers, `agentvetter setup-agent-hooks`, and five `/av-*`
skills (aliases `/tw-*`) landed on `main` via Phase 1 agent-hooks (see
`agent-hooks/`). **Slice 28**
(`/av-verify` / alias `/tw-verify` Quality `N/100` + blocked footer + Sources: Tessl Quality /
Cisco+Snyk Status) is ✅ **PASSED** on `main`
([#118](https://github.com/neomatrix369/AgentVetter/pull/118)) — contract SSOT
[frontline-output-contract.md](./user-guide/frontline-output-contract.md) —
formal close 2026-09-21. Formal Must gate-evidence closures for **23–27 / 29–32**
still lag. Slice **35** Ossprey access remains 🔴. ADR-0015 Horizon A exclusion
is amended by ADR-0017; full Guard VERIFIED still waits on Phase-1
regression-gate evidence (slice 32).

**Wave L — Tessl 5-row expansion (2026-08-25):** Row 3
(`"Tessl: Scenario Generation"`) is **IMPLEMENTED (unit, slice 49 ✅ #112)** —
`scenario generate <plugin-path> --count 3` → `scenario download <gen_id> -o
<plugin>/evals/` with `resume_checkpoint` + mid-scan persist. Row 4
(`"Tessl: Eval"`) is **IMPLEMENTED (unit, slice 50 ✅ #113)** — starts `blocked`,
auto-chains when generation completes and `evals/` is populated; stale on
scenario re-run; resume via `eval view`. Row 5 (`"Tessl: Review (Security)"`)
is **IMPLEMENTED (unit, slice 51)** — `review run security` after Eval;
`upstream_run_ids.review_quality` from ctx; dashboard shows linked Quality
findings on the expanded Security row. Coverage Gap B (`scenario view <id>`)
resolved; Gap C (agent-assisted generation) open. **VERIFIED (slice 48 ✅
[#110](https://github.com/neomatrix369/AgentVetter/pull/110); packing re-check
2026-09-21):** host `evals/` is not a vuln-scan input — `_pack_local_dir` /
`_copy_local` omit root `evals/` when the skill root has `tessl.json` or
`.tessl-plugin/`. Git clone and identity hash still see on-disk `evals/`. Spec:
[design/tessl-5-row-expansion.md](./design/tessl-5-row-expansion.md),
[slices 49–51](./plan/slices/12-L-tessl-5-row-expansion/).

**Wave M — LLM usage / cost observability (2026-08-25):** Group **13-M** (letter after L).
Meter router (SIE + Model Studio) accurately; Phase 2 best-effort Cisco/Tessl events;
dashboard Usage tab + cost tips. **DECIDED** as plan-only slice 53 — design and stub
captured; **not IMPLEMENTED**. **Not** filed under J (dashboard quality A1–A13 ✅),
L (Tessl rows), or G (ATDD parked). Spec:
[design/llm-usage-tracking.md](./design/llm-usage-tracking.md),
[slice 53](./plan/slices/13-M-llm-usage-tracking/slice-53-llm-usage-tracking.md).
Dedicated usage table — does **not** resurrect deferred `agentvetter.audit`.

**Wave O — Monk Kit Live packaging (2026-09-09):** Group **15-O**. Package AgentVetter
as a Monk Kit (Tier 1 MVL = Supabase + Modal; Tier 2/3 scanners per ADR-0001).
**DECIDED** as plan-only (**O0** governance + slices 58–61) on branch
`docs/monk-kit-wave-o`; ADR-0001 remains **Proposed** until O0 Accept HITL.
**Not IMPLEMENTED** — no Kit on `main`; workstation Live path unchanged. Spec:
[ADR-0001](./adr/0001-monk-deployment-and-packaging.md),
[phase-O0](./plan/slices/15-O-monk-kit-live-packaging/phase-O0-governance.md),
[TRAIL Wave 15-O](./plan/TRAIL.md).
**Wave P — Git repo discover + fan-out (2026-09-09; package path 2026-09-20):** Group **16-P** (letter after N;
**O** reserved for Monk Kit plan on `docs/monk-kit-wave-o`). GitHub repo URL (root or
`/tree|/blob/…` browse URL) → normalize to cloneable repo root → discover **skills and
MCPs** → **N separate scans** with scanners by `item_type`; dashboard cards carry
skill/MCP **name** (SKILL.md frontmatter when set; repo-relative path when leaf equals
repo) plus `org/repo` signature (`identifier` = `org/repo/<relpath>`); re-scan refreshes
`items.name` even on content-hash hits. **Slice 64:** when package manifests exist at
scope root, also emit a **`package`** target (`items.type=package`, Accepted) so DepShield /
Ossprey / Snyk run — not a fake skill; Cisco Skill / Tessl / Cisco MCP do **not** apply;
package Snyk uses **`snyk test` SCA** (Agent Scan only covers skills/MCP); Rust/Cargo
trees are `not_applicable` for Snyk SCA and DepShield (npm+PyPI only) — that gap
stays explicit; RustSec **Cargo Audit** covers `Cargo.lock` / `Cargo.toml` when
installed (**IMPLEMENTED** on `main`; slice 72 formalizes the gap-scanner path —
not a deferred “full Cargo coverage” placeholder). All-N/A complete → NO COVERAGE
not green; repos with neither skill/MCP **nor** manifests still fail closed.
**Slice 63:** CLI prints scanner inventory + rollup after scan / zero-artifact
(package expected sources = Snyk/DepShield/Ossprey (+ Cargo Audit)). Slices 62–64 ✅
landed `main` via
[#145](https://github.com/neomatrix369/AgentVetter/pull/145) /
[#146](https://github.com/neomatrix369/AgentVetter/pull/146). Cargo SCA honesty
merged via [#147](https://github.com/neomatrix369/AgentVetter/pull/147); coverage
ledger (slice 65) absorbs that honesty — never claim fully scanned for
Cargo-only when no scanner completed.
Operator taxonomy soft-amended in slice **56-a**
([prerequisites — What can AgentVetter scan?](./user-guide/prerequisites.md#what-can-agentvetter-scan)).
Spec:
[slice 62](./plan/slices/16-P-git-repo-scan/slice-62-git-repo-discover-fanout.md),
[slice 63](./plan/slices/16-P-git-repo-scan/slice-63-cli-scanner-inventory.md),
[slice 64](./plan/slices/16-P-git-repo-scan/slice-64-git-repo-package-scan.md),
[plan/TRAIL.md](./plan/TRAIL.md) Wave 16-P.

---

## PROPOSED

Claude Code agent-hooks integration layer — **Phase 1 SUPERSEDED by shipping on
`main`** under [agent-hooks](../agent-hooks/README.md). **H0 governance ✅**
(2026-09-21). Slice 28 Quality/`N/100` and Sources attribution is ✅ **PASSED**
on `main` (#118; formal close 2026-09-21 — see [DECIDED](#decided) Wave H).
Formal Wave H Must gate closures (23–27, 29–32) and the ADR-0017 Phase-1
regression matrix remain open.

ADR context ([ADR-0017](./adr/0017-claude-code-agent-guard-integration.md)
amends [ADR-0015](./adr/0015-horizon-a-excludes-guard-and-drift.md); Drift/trend
remains Won't (A)):

- PreToolUse enforcement handler at `~/.agentvetter/hooks/` (`pre-tool-use.sh` +
  `_guard_entry.py`; repo source `agent-hooks/hooks/`) — fail-closed decision
  JSON with internal timeout budget, identifier lookup + CLI-compatible hash
  comparison, 14-day staleness window — **SUPERSEDED → on `main`** (live
  regression matrix still open)
- Five `/av-*` skills (`av-verify`, `av-scan`, `av-enable`, `av-disable`,
  `av-self-check`; permanent `tw-*` aliases; repo source `agent-hooks/skills/`,
  installed to `~/.claude/skills/`) — **SUPERSEDED → on `main`** (Quality column: slice 28)
- `agentvetter setup-agent-hooks` installer (preflight, `~/.agentvetter/config.json`
  init, handler install, env pre-warm, `~/.claude/settings.json` JSON-merge,
  skill copy, bootstrap scan sweep) — **SUPERSEDED → on `main`**
- Local `enable` kill switch AND-ed with Supabase `monitoring_enabled`;
  missing/corrupt local config denies (tamper signal) — **SUPERSEDED → on `main`**

Full IMPLEMENTED/VERIFIED for Horizon A still requires the Phase-1
regression-gate evidence (live block/allow matrix, tamper case, fail-closed
refusal+hang pair, settings diff) — see ADR-0017 Consequences.

---

## RESEARCH (not VERIFIED)

Exact JSON field names in `sandbox/scanners.py` — cross-check against the pinned
CLI version's `--help`/output before this blocks a merge. See
[scanner-output-adapters.md](./research/adapters/scanner-output-adapters.md).
Adapter fixture tests (slices 8–9) are planned to tighten this.

Ossprey OSSBOM / exit-code malware signal mapping remains RESEARCH until a live
`ossprey-cli` probe reconciles the adapter against the pinned CLI (see IMPLEMENTED
bullet + adapters doc §8).

---

## Future (not current behaviour)

Known fixture gaps (not urgent) are listed under
[fixtures/README.md](../fixtures/README.md) (“Not yet built”). Do not treat those
as shipped capabilities. Guard PreToolUse and Drift/trend remain Future /
Won't (A) for the Horizon A ship path — see
[ADR-0015](./adr/0015-horizon-a-excludes-guard-and-drift.md). Frontline Guard
Phase 1 (hooks + `/av-*` skills, aliases `/tw-*`) is on `main` under `agent-hooks/`; **H0 ✅**;
slice 28 Quality dual-output is ✅ **PASSED** on `main` (#118). Formal
Wave H Must gate closures (23–27, 29–32) remain open.

Coverage audit matrix: [plan/coverage-audit.md](./plan/coverage-audit.md)
(slice 7 ✅). Slice stubs: [plan/README.md](./plan/README.md) (`01-A-…` …
`16-P-git-repo-scan/`). Wave G (slices 18–22) is planned ATDD closure
(parked while Wave H Musts run). Wave H (23–39) trackers: Phase 1 code on
`main`; H0 ✅; slice 28 ✅; formal product ✅ closures still mostly open for
23–27 / 29–32. Claim
audit (slice 15) and slice 16 remediations are deferred; retain their artifacts
for a future live/demo release. Wave M (slice 53) LLM usage log / cost tips is
**DECIDED** plan-only — see DECIDED above; not current dashboard behaviour.
Wave O (Monk Kit, ADR-0001 Proposed / plan **O0**+58–61) is **DECIDED**
plan-only — not current deploy behaviour; workstation Live remains supported.
Wave P (slices 62–64) git repo skill+MCP fan-out, CLI scanner inventory, and
package/DepShield/Ossprey targets is ✅ on `main` (#145/#146). Cargo-only SCA
honesty (all-N/A → NO COVERAGE) is VERIFIED on Live for the zero-engine path;
RustSec Cargo Audit is **IMPLEMENTED** on `main` for Cargo.lock/toml when
installed (slice 72 formalizes). Feeds Wave R slice 65 ledger — see DECIDED above.
