# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Docs
- Migration guide: Modal secrets + `agentvetter-scan` deploy, Supabase
  `agentvetter_rollup_item`, and Pages demo path cutover recorded as **VERIFIED**
  (maintainer workspace 2026-10-02); operator checklist updated. See
  [docs/MIGRATION-AGENTVETTER.md](docs/MIGRATION-AGENTVETTER.md).
- README hero image: `AgentVetter-Banner.png`; GitHub badge/clone links use
  `neomatrix369/AgentVetter`.
- Screenshot gallery regenerated 2026-09-21 (post-rebase onto `main`): Mock
  Dashboard + new Workflow Run/Triage/Verify shots, quality floors, R/Q badges;
  live CLI scan refresh; capture script covers `05-workflow/`
### Fixed
- Schema cleanup: `db/schema.sql` now drops `tripwire_rollup_item(uuid)` via
  `DROP FUNCTION IF EXISTS` so `agentvetter setup --force` idempotently removes
  the legacy function on any older deployment. Dropped from live Supabase DB
  (2026-10-08). No code called the old function. PR: [#188](https://github.com/neomatrix369/AgentVetter/pull/188).
- Dashboard item drawer: Findings, Modal console output, and Raw output start
  collapsed so stored scanner runtime is not dumped open by default.
- Dependency CVEs blocking PR checks: `pyjwt` → 2.15.1, `urllib3` → 2.8.0,
  `virtualenv` → 21.14.5 (`uv.lock`); `brace-expansion` → 5.0.12
  (`cli/package-lock.json`).
- Workflow L→R smoke FAIL/PARTIAL (slice 77, on
  `slice/77-workflow-smoke-fix-target-flow`): Run “Review findings” CTA treats
  `not_applicable` / `blocked` as finished; process line only says “running”
  when active statuses exist; finding stable ids include target identity +
  dedupe so Triage/Fix/Report share one universe; `stableFindingId` is
  idempotent so Triage To fix / Needs review / Dismiss prefs apply after save;
  single finding select after focusing one skill/MCP/package; Verify no longer
  claims “Finding gone” for heuristic patches until Mark fixed. VERIFIED
  (unit GWT-77.* + Mock/Live browser smoke 2026-09-21). Spec:
  `docs/plan/slices/18-R-approved-repo-workflow/slice-77-workflow-smoke-fix-target-flow.md`.
- Triage SCA rows: show lockfile path in the title (`pkg@ver · CVE · path`) and
  collapse exact duplicate inserts (`×N`) so monorepo package findings are
  distinguishable — vibe-kanban braces/adm-zip no longer look identical.
  `agentvetter-triage.js` + Triage row meta line.
- Package / SCA honesty for unsupported ecosystems (Cargo-only and similar):

  `snyk test` does not support Rust/Cargo — AgentVetter reports `not_applicable`
  with an explicit ecosystem detail instead of a false clean. When every
  applicable scanner is `not_applicable` / skipped (zero completed engines),
  `agentvetter_rollup_item` stays grey and the Live dashboard paints
  **NO COVERAGE** (not UNSCANNED — a scan ran; no engine scored). Never GREEN /
  `R 0.00`. Partial-failed with zero completed engines remains ERROR.
  Dashboard: `agentvetter-status.js` / `agentvetter-live.js`; rollup: `db/schema.sql`;
  Snyk preflight: `sandbox/scanners.py`. VERIFIED on Live Packages (pizauth / snare).

### Added
- Dashboard Workflow chrome polish (slice 76, Wave R) — IMPLEMENTED / VERIFIED
  (unit) on `main` ([#165](https://github.com/neomatrix369/AgentVetter/pull/165)).
  Denser Triage filter toolbars with Type/Quality/Target/Status group labels,
  shared `tw-panel-*` typography tokens across Run→Report, and plain-language
  Triage override buttons (“To fix” / “Needs review” / “Dismiss”). Filter
  semantics unchanged (`GWT-73.*`). Spec:
  `docs/plan/slices/18-R-approved-repo-workflow/slice-76-workflow-chrome-polish.md`.
- Dashboard Workflow operator-visible pipeline narration (slice 75 / R-UX-1,
  Wave R) — IMPLEMENTED / VERIFIED (unit) on `main`
  ([#163](https://github.com/neomatrix369/AgentVetter/pull/163)). Workflow UI
  narrates judge-panel honesty (no fabricated pending slots; panel-off / absent
  copy), prefers CLI coverage ledger, builds Run process line + “Review findings”
  CTA, Investigate final-judge / evidence honesty, keeps Fix free of false
  `gen-27b` hints, and completes the L→R soft-amend: parent type·name on
  findings, keyboard multi-select with `k of N` progress, and role-labelled /
  parent-attributed model lines. Modules: `agentvetter-workflow-pipeline.js`,
  `agentvetter-workflow-models.js` (+ Workflow HTML wiring); GWT-75.1–75.11 tests.
- Dashboard Triage: type + quality + per-target filters (slice 73, Wave R) —
  IMPLEMENTED / VERIFIED (unit) on `main`. Same inventory-style type buttons
  (All / Skills / MCP / Packages), quality tabs (including All quality), and
  per-target chips so operators can narrow issues before Fix. Filters compose
  with status tabs; finding rows show the target name. SCA rows use
  `package@version · CVE` titles instead of repeating `dependency_vulnerability`
  (Live also passes through `package_name` / `package_version` / `cve_ids`).
- Dashboard workflow model labels (slice 74, Wave R) — ✅ PASSED (formal close
  2026-09-20). Stepper tabs show role-aware default model aliases (Run
  panel light/mid + final stronger `gen-4b · gen-27b`, Triage SIE `gen-4b`,
  Investigate SIE/MS `gen-4b · qwen3.8-max`; Fix blank while propose is
  heuristic). Run / Triage / Investigate / Fix panels show actual models from
  judge slots, router envelope, or fix provenance when an LLM ran, with
  type·name parent prefix when a finding is in context
  (`agentvetter-workflow-models.js`; GWT-74.1–74.5).
- Dashboard Verify step: worktree rescan honesty (slice 70, Wave R) —
  IMPLEMENTED / VERIFIED on `main` (#155). Re-applies the proposed patch on a
  temp copy only, re-runs applicable scanners via port, and reports
  **finding gone** / **still present** / **unable to verify** (with reason +
  scanner actions). Missing/failed/timeout scanners never map to finding gone;
  generation alone never claims fixed. Approved repo stays unchanged.
- Dashboard Fix step: proposed minimal patch + apply-clean on a temp copy
  (slice 69, Wave R): `agentvetter-fix-propose.js`, `agentvetter-apply-clean.js`,
  `agentvetter-fix-controls.js` — landed `main` (#154). Operator can copy the
  diff / `git apply` command, mark fixed or won't-fix (reason required), and
  move with J/K. Proposed patches never auto-modify the approved repo and
  never claim the finding is verified/fixed from generation alone. GWT-69.*
  tests in `prototypes/dc-dashboard/test/agentvetter-fix*.test.js`.
- Dashboard Expert view + Report export (slice 71, Wave R): Expert toggle shows
  raw judge answers, model IDs, confidence, weakness/AI-sec IDs, scanner details,
  and data-flow; Report step summarises fixed / left / won't fix with primary
  JSON export (+ Markdown) including coverage ledger; secrets masked unless
  explicitly revealed. Modules: `agentvetter-report.js`, `agentvetter-report-export.js`;
  GWT-71.* tests — landed `main` (#153).
- Dashboard workflow stepper Run→Triage→Investigate (slice 68, Wave R):
  prototype modules under `prototypes/dc-dashboard/` (`agentvetter-workflow-*`,
  run-progress, triage, investigate) with GWT-68.* tests — landed `main` (#152).
- SIE judge panel CLI + module (slice 67, Wave R): `agentvetter judge
  --batch-id <id>` → `runJudgePanel` (`cli/src/judgePanel.js`); mocked unit tests
  in `cli/test/judgePanel.test.js`. Model inventory documented (`gen-4b` /
  `gen-27b`; fewer than 3 models → parallel same-model runs). Optional soft-fail
  post-route hook only when `AGENTVETTER_JUDGE_PANEL=1` (default off; ADR-0016 route
  unchanged).
- Evidence verify + injection guard (slice 66, Wave R): host-side check that
  quoted finding text exists at path:line (`evidence_verified` vs fail-closed
  `unverified`); deterministic hidden/encoded instruction detection; scanned
  content wrapped as untrusted data for judge/prompt channels; secrets masked
  unless `agentvetter scan --reveal-secrets`. CLI prints `[evidence]` on scan and
  `--dry-discover` for skill/MCP targets (`cli/src/evidenceVerify.js`).
- Language/ecosystem coverage ledger (slice 65, Wave R): `agentvetter scan` and
  `--dry-discover` print `[coverage]` rows (ecosystem, volume, scanner, status,
  unsupported portions, reason). Marker-driven; reuses DepShield/Snyk/Ossprey/
  Cargo Audit — no invented scanners. Cargo-only honesty absorbed from #147;
  rollup never claims fully successful when ecosystems lack a completed scan.
  Local checkouts with package manifests emit a `package` target.
- **Cargo Audit** (RustSec `cargo-audit`) SCA adapter for `Cargo.lock` /
  `Cargo.toml` trees — registered in `SCANNER_GROUPS` between DepShield and
  Ossprey; Modal image installs `cargo-audit`. Prefer real RustSec over LLM
  Rust analysis (LLM deferred). Package inventory expects Cargo Audit alongside
  Snyk / DepShield / Ossprey. Slice **72** (Wave R Could) formalizes this as the
  Rust/Cargo gap scanner: production path **IMPLEMENTED** on `main`; Snyk SCA +
  DepShield Rust gaps remain explicit (not claimed fixed by this adapter).
- GitHub repo discover + fan-out (slice 62, Wave P): `agentvetter scan https://github.com/org/repo`
  (and `/tree|/blob/` browse URLs) shallow-clones on the host, walks skills (`SKILL.md`)
  and MCP roots (`server.py`/`server.js`/`run.sh`), emits N typed targets with
  `identifier=org/repo/<relpath>` and dashboard cards titled by **skill/MCP name**
  (SKILL.md frontmatter when set; never bare repo name when leaf equals repo) plus
  `org/repo` signature. Soft-amend prerequisites Git URL taxonomy (56-a).
- Git repo **package** target + DepShield/Ossprey/Snyk path (slice 64, Wave P): when
  package manifests exist at scope root, discovery also emits one `items.type=package`
  target (`identifier` `org/repo` or `org/repo/@package` on collision) — not a fake
  skill; Cisco Skill / Tessl / Cisco MCP do not apply. Repos with neither skill/MCP
  **nor** manifests still return `[]` (fail-closed). Schema check widens
  `items.type` to include `package`. Dashboard type filter adds Packages.
- CLI scanner inventory after scan (slice 63, Wave P): `agentvetter scan` prints
  `[scanners]` per-source status + rollup (`fully successful` / `partly successful` /
  `fully failed` / `not run`) after dispatch and on zero-artifact explicit targets
  (registry listed as `not_run`). Package expected sources = Snyk / DepShield /
  Cargo Audit / Ossprey.
- Docs: Wave **16-P** git repo discover + fan-out plan (slices 62–64) —
  [slice 62](docs/plan/slices/16-P-git-repo-scan/slice-62-git-repo-discover-fanout.md),
  [slice 63](docs/plan/slices/16-P-git-repo-scan/slice-63-cli-scanner-inventory.md),
  [slice 64](docs/plan/slices/16-P-git-repo-scan/slice-64-git-repo-package-scan.md),
  TRAIL/PROGRESS/STATUS. Soft-amend slice 56-a taxonomy.
- `/tw-verify` Quality column + blocked footer (slice 28): Scan Status table is
  **Name | Type | Status | Quality | Note**; Quality shows Tessl
  `items.quality_score` as **`N/100`** (else `—`); shared
  **Will be blocked when AgentVetter is enabled** appears once under the table;
  **Sources** line attributes Quality to Tessl and security Status to
  Cisco AI Defense and Snyk. Shared helpers in `guard/verify.py`; contract SSOT
  [frontline-output-contract.md](docs/user-guide/frontline-output-contract.md).
  Re-run `agentvetter setup-agent-hooks` to refresh installed skills.
- Docs: Wave **13-M** LLM usage / cost observability plan (slice 53) —
  [design/llm-usage-tracking.md](docs/design/llm-usage-tracking.md), slice stub,
  TRAIL/PROGRESS/STATUS DECIDED (not IMPLEMENTED). Historic collapsible Usage
  log + router metering — build only when slice execution starts.
- Tessl Review (Security) scanner row (slice 51): `run_tessl()` emits
  `"Tessl: Review (Security)"` after Eval via `_run_tessl_review(judge_type="security")`
  (`tessl review run security --json --workspace`); `upstream_run_ids.review_quality`
  is attached before invoke; Security `tessl_run_id` via `review view --last --json`.
  Expanded Security row shows linked Quality findings when that ID is populated
  (UI-level; live Tessl fetch is slice 52).
- Tessl Eval auto-chain scanner row (slice 50): `run_tessl()` emits
  `"Tessl: Eval"` as `blocked`, then auto-chains after Scenario Generation when
  `<plugin>/evals/` has scenarios — `tessl eval run --runs 3 -y --json` +
  `eval view` poll, `upstream_run_ids`, project create/repair preflight; scenario
  re-run marks prior completed Eval `stale` (no cascade).
- Tessl Scenario Generation scanner row (slice 49): after Review (Quality),
  `run_tessl()` runs plugin-path `tessl scenario generate --count 3`, downloads
  into `<plugin>/evals/`, stamps `tessl_run_id` / `upstream_run_ids`, and persists
  `resume_checkpoint` mid-scan for Modal detach/resume.
- Dashboard Tessl "Not Available Yet" placeholders (slice 48): Scanner Outputs
  merges a static list of five Tessl capabilities and renders missing
  Scenario Generation / Eval / Review (Security) as muted UI sentinels
  (no chevron, no DB insert). Header count includes the placeholders.
  MCP scans without Tessl rows are unchanged. Tessl plugin pack/copy omits
  host root `evals/` (`tessl.json` or `.tessl-plugin/` marker); non-Tessl
  trees keep `evals/`.
- Tessl Review (Quality) run-ID capture (slice 47): `_run_tessl_review(judge_type="quality")`
  runs `tessl review run quality --json --workspace` (replaces deprecated
  `tessl skill review`) then `tessl review view --last --json` to persist
  `tessl_run_id` + `tessl_run_id_at`. After stamp, `_update_tessl_id_context`
  sets in-process `ctx["review_quality"]` (GWT-47.5) for slices 49–51.
  Missing `TESSL_WORKSPACE` → `needs_setup`. Lint stays outside the ID chain.
- Tessl Lint adapter (slice 46): `run_tessl()` writes a `"Tessl: Lint"` row via
  `npx tessl@latest skill lint` (auth-free, synchronous, no `tessl_run_id`)
  before `"Tessl: Review (Quality)"`. Missing `TESSL_TOKEN` still runs Lint and
  marks Review `needs_setup`. Dashboard Mock/Live bind quality badges to Review
  only. Live CLI probe 2026-08-24: lint validates plugin packages; skill-folder
  fixtures exit 1. Live success stdout `✔ Plugin … is valid` maps to `checks_run=1`.
  Live persist VERIFIED 2026-08-24: scan_run `a36cad9f` wrote Lint `failed`
  (no plugin manifest on the SKILL.md-only fixture) and Review `completed`
  (quality_score 64).
- `agentvetter status [--json] [--limit <n>]` — read-only monitoring report (slice 37):
  agent-hook install/enable state with the two-switch view (local `enable` AND Supabase
  `config.monitoring_enabled`, disagreement warned), items heatmap distribution, recent
  scan-run health with stranded-`running` detection (>30 min Modal-timeout strand;
  remedy `scripts/reconcile-stuck-scan-runs.mjs`), and latest per-scanner status.
  Degrades to local-only hooks output when Supabase credentials are missing (exit 0);
  invalid flags exit nonzero with an actionable message
- Landing intro screen shown on first dashboard open (sessionStorage-persisted toggle);
  surfaces threat statistics, SEC/01–SEC/05 narrative sections (anatomy of breach,
  architecture flow, RAG status card grid, shipped `/tw-*` skills, roadmap), animated
  ticker bar, and `$ agentvetter setup-agent-hooks` install CTA. "About" nav button toggles
  the intro at any time.
- Dashboard visual restyle (slice 41, superseded by v2 above): JetBrains Mono, cyan
  `#00D9FF` accent, darker panel palette, body grid overlay, and HUD corner brackets.
- `agentvetter scan --type <skill|mcp>` — restricts machine-wide discovery to a single artifact
  category without changing any other scan behaviour; composes with `--dry-discover`,
  `--force`, `--concurrency`, and explicit path arguments

### Changed
- Hard-cut residual legacy product names from live code/docs (ADR-0018 amend
  2026-10-03): single CLI bin `agentvetter`; config home `~/.agentvetter` only;
  `AGENTVETTER_*` env only; schema ships `agentvetter_rollup_item` only;
  permanent `tw-*` skill aliases retained.
- Operator Modal cutover (ADR-0018): live secrets `agentvetter-supabase` /
  `agentvetter-scan-secrets`; deployed app `agentvetter-scan`. VERIFIED smoke scan
  `fixtures/skills/safe-csv-cleaner` after rollup apply (2026-10-02).
- Agent brand surfaces (slice 78): live skills, guard remedies, and
  `setup-agent-hooks` summary prefer `/av-*` (permanent `tw-*` aliases retained).
  IMPLEMENTED / VERIFIED (unit) on `slice/78-agent-brand-surfaces`.

- **Breaking — rebrand to AgentVetter** (ADR-0018): packages `agentvetter` /
  `agentvetter-cli`; skills `av-*` (permanent `tw-*` aliases); config home
  `~/.agentvetter`; env `AGENTVETTER_*`. See
  [docs/MIGRATION-AGENTVETTER.md](docs/MIGRATION-AGENTVETTER.md).
- Dashboard primary navigation: inventory (KPIs / filters / cards) is the default
  **Dashboard** tab; Run → Triage → Investigate → Fix → Verify → Report lives on a
  secondary **Workflow** tab (`prototypes/dc-dashboard/AgentVetter.dc.html`). Simple/Expert
  remains a Workflow-only density toggle (finding detail), not a gate that hides
  inventory. IMPLEMENTED on `main`
  ([#160](https://github.com/neomatrix369/AgentVetter/pull/160)).
- CI ultra-minimal (parity with quine-factory, **USER-CONFIRMED** 2026-09-11):
  PR/push keep ship-path coverage + OSV + targeted Trivy/gitleaks/TruffleHog;
  Semgrep, CodeQL, Meterian, dashboard prototype tests, and full-history scans
  move to **A** `nightly.yml` (daily 02:00 UTC) or **B** `supply-chain.yml`
  (weekly Mon 03:00). Removed Mon 03:00 CI T3 re-run cron. Code Review Graph
  runs on the nightly schedule (PR sticky comments dormant). Docs: ADR-0013,
  CONTRIBUTING, docs hub, README, STATUS, ARCHITECTURE, DECISIONS,
  coverage/claim audits + TRAIL/slice soft-amends.
- T4 cloud split into three workflows (**USER-CONFIRMED**): **A** `nightly.yml`
  Light T4 **daily 02:00 UTC** (cov snapshots, complexity, TruffleHog full, dep
  audit); **B** `supply-chain.yml` **weekly Mon 03:00 UTC** (SBOM, Meterian
  strict, Chalk); **C** `mutation.yml` **1st+15th 04:00 UTC** (Stryker +
  advisory mutmut, non-gating). Supersedes the short-lived “all Nightly jobs
  twice monthly” monolith. CI’s Mon 03:00 cron remains a separate T3 re-run.
- Docs: socialise hosted dashboard
  ([neomatrix369.github.io/demos/agentvetter-dashboard/](https://neomatrix369.github.io/demos/agentvetter-dashboard/))
  and demo walkthrough video
  ([YouTube](https://youtu.be/omGOw9ruN3Y)) across README, QUICKSTART, docs hub,
  architecture, prototypes, screenshots, setup commands, and prerequisites.
- README restored to the fuller pre–slice-44 entry shape and brought current:
  providers/scanners table (Modal, Supabase, Cisco, Snyk, Tessl five-row,
  DepShield, Ossprey, SIE, Model Studio), hosted demo link, Live setup, guide
  map, screenshot grid. Trust-strip gate superseded for Ossprey on README
  (`ossprey-readme`); Overmind still forbidden. Sync-docs also aligned
  ARCHITECTURE inventory + diagrams, STATUS, QUICKSTART, prerequisites,
  CONTRIBUTING, setup-commands.
- Dashboard detail drawer **Findings** section is collapsible: clickable heading with
  a rotating ▸ chevron (expanded by default on item select). Same expand pattern as
  Scanner outputs rows — `prototypes/dc-dashboard/AgentVetter.dc.html` (IMPLEMENTED).
- Public docs UX + compaction (slice 44): README/QUICKSTART lead with plain language,
  demo-first (Recommended) then Live (Advanced); badges behind disclosure; path map
  absorbed into QUICKSTART. Merged `sie-setup` + `model-studio-setup` into
  `docs/user-guide/tiered-router-setup.md`. Removed thin aliases
  `onboarding-cheatsheet.md` and `path-commands.md`. Glossary / CLI flags / fail hints
  absorbed into reading-router-results and setup-commands; docs hub links agent-hooks.
  Pile-on: Setup (accounts) vs Configure (keys) beats; loud Minimum Viable Live
  (Supabase + Modal); Maintain hub row; Daily maintenance cheat lines; screenshots
  note `R`/`Q` colour ≠ density. ARCHITECTURE adds External services inventory plus
  operator-journey and dependency-order Mermaid diagrams.
- Dashboard visual identity v2 (slice 43): warm cream paper field (`#F5F2EA`), tan
  primary CTA (`#C4A574`), Fraunces serif on intro `h1`/`h2`; cyan `#00D9FF` kept as
  live **signal** only (SENSOR dots, wire pulse, scanning fills). Status labels, links,
  and muted chrome use AA **ink** tokens on paper (`--red-ink` `#B42318`, `--cta-ink`
  `#7A5C2E`, `--text-muted` `#6B645A`, and peers). Modal console and finding snippets
  on `--bg-deep` use readable ink/secondary text (not HUD terminal neon). Partial-scan /
  disagreement callouts and Guard result banners use `--violet-ink` / status ink (not
  dark-theme pastels like `#d4bcff`). AgentVetter HUD brackets, grid overlay,
  and RAG fill colours retained. Supersedes slice 41 dark-cyan fill.
- Dashboard operator chrome (slice 42 A9–A13): skill cards show Tessl `Q N` / `Q —` /
  `Q ?` with hover explaining 0–100 skill-review quality; risk uses compact `R N.NN`
  badge (parity with Q) plus density tooltip; list column stays **Risk density**;
  locus/availability chips use plain language (`On disk`, `No local source`, …).
  Risk/quality hints use a fixed `#score-tip-portal` (viewport-clamped) fed by
  `.score-tip` / `.score-tip-bubble` text — escapes grid `overflow` clipping and
  avoids delayed native `title=` attributes.
- Dashboard quality triage tabs (slice 42 A14–A15): toolbar **Quality ≥ 80**,
  **Quality < 80**, and **No quality score** tabs filter skills by Tessl
  `item.quality` (threshold 80); tab labels include skill counts; empty-state
  copy names the active tab; **Clear filters** resets quality tab to default.
  MCP servers are excluded from quality buckets (no score) but remain visible
  on all quality tabs. Helpers in `agentvetter-status.js`; wired in `AgentVetter.dc.html`.

### Fixed (schema, naming, Tessl progress, live fleet)
- Schema bootstrap for existing DBs (slice 64 follow-up): `ensureSchema` probes live
  `items_type_check` and re-applies `db/schema.sql` when `package` is missing from the
  CHECK; the widen `DO` block no longer swallows errors with `exception when others`.
  Pre-package projects no longer silently keep rejecting `INSERT type='package'`.
- Re-scan refreshes dashboard card **`name`** even when content hash is unchanged
  (`upsertItem` updates `items.name` on hash hits and identifier reuse). Stale
  titles from pre–naming-contract rows no longer require `--force` or a manual
  SQL rewrite solely to rename cards.
- Tessl dashboard progress during Modal scans: skip bulk `running` placeholders for
  all five Tessl rows at group start; Lint and Review (Quality) now persist
  `running`→terminal via `on_scanner_progress` so only the active step shows
  Running. Dashboard adds status pills for `blocked`, `stale`, `interrupted`, and
  `timed_out` (`agentvetter-status.js`).
- Live dashboard latest-state accuracy (partial slice 21): `db/schema.sql` adds
  `dashboard_latest_runs` view (`DISTINCT ON (item_id)`); `agentvetter-live.js` queries
  it instead of a global `scan_runs?limit=2000` page and batches
  `scan_run_scanners` / `findings` fetches (~40 run IDs per request) to stay under
  PostgREST **Max rows**. Historic `scan_runs` rows are retained. Operator:
  `agentvetter setup --force` after upgrade; optional Max rows raise —
  [supabase-setup § Data API max rows](docs/user-guide/supabase-setup.md#6-data-api-max-rows-live-dashboard-fleet-size).
- Live dashboard **Scanner outputs** drawer pills sort **A–Z by scanner source**
  (Live + Mock); order no longer follows DB insert sequence.

### Fixed (dashboard data quality — slice 42)
- Dashboard per-item latest run selection (slice 42 A1): superseded for Live load
  path by `dashboard_latest_runs` view above; the interim `limit=2000` global page
  fixed ~35+ cards that incorrectly showed "never scanned" / 0 findings when the
  true latest run fell outside the window
- `findings` and `scan_run_scanners` fetches are now scoped to the latest run IDs per item
  rather than full-table scans; eliminates network-level waste on every dashboard load (A2)
- MCP server discovery (`cli/src/discovery.js`) now resolves `install_locus` and
  `source_availability` from the manifest entry instead of hardcoding `unknown/unknown`:
  entries with a resolvable `packPath` get `local/source_on_disk`; bare-binary entries
  (e.g. `npx context7`) get `local/introspection_only` (A3)
- ERROR cards now display "Scan run failed — no findings available" in the Findings
  section header instead of the misleading bare "Findings (0)" (A5)
- Tessl scanner logs a structured `[tessl]` diagnostic line when `_tessl_quality_score`
  cannot extract a value from the CLI JSON output, aiding root-cause analysis for the
  7 skills currently showing `NULL quality_score` (A4)
- Reconciled 9 scan_run rows stuck in `status=running` since Aug 1–16 (A6)

## [0.4.0] - 2026-08-14

### Added
- Tiered post-scan router: `agentvetter route` and auto-route after `agentvetter scan`
  (SIE triage + optional Model Studio escalation; `scanner_source=tiered_router`)
- Model Studio and SIE sample CLIs under `prototypes/model-studio/` and
  `prototypes/sie-studio/`
- Dashboard router strip, SIE-only / escalated filters, and Mock router fixtures
- Optional `.env` keys for SIE / Model Studio (documented in `docs/user-guide/env-vars.md`)
- ADR-0016: tiered router via SIE and Model Studio

### Changed
- Card `heatmap_status` is worst-of actionable findings (any red → red; amber-only
  → amber); `risk_score` stays weighted density for sort/trend. Dashboard cards
  show an actionable finding-count chip so one vs many vulns stay distinguishable
- Severity rollup excludes `tiered_router` findings so triage does not inflate
  scanner red/amber counts
- CLI coverage floors temporarily lowered (60/60/80/60) while measured CLI
  coverage recovers after the router land; `cli/test/router.test.js` exists;
  ADR-0013 ≥95% target unchanged

### Fixed
- Tiered router no longer batch-deletes `tiered_router` findings before routing;
  per-item replace-on-success preserves `Scan → SIE → ■` strips when SIE skips
- Dashboard shows `Scan → ■` / “SIE not called” on scanned cards with no
  `tiered_router` finding (SIE never invoked)

### Docs
- Formal ADR catalog under `docs/adr/`: Accepted retrospective records
  0002–0016 for shipped topology, scanning, security, CLI, quality,
  Horizon A scope, and tiered router. Number 0001 reserved (Monk Live packaging
  draft on a side branch, not published). Indexes wired from Architecture,
  STATUS, README, QUICKSTART, CONTRIBUTING, and plan README.
- Provider setup guides for optional tiered routing:
  `docs/user-guide/sie-setup.md` and `docs/user-guide/model-studio-setup.md`
  (wired from README, QUICKSTART, docs index, env-vars, prerequisites)
- Operator howto for pathway strips / Escalated / SIE-only / categories:
  `docs/user-guide/reading-router-results.md`
- README “What happens next” / “Find the right guide” now map the full stack
  (Discover→Scan→Store→Route→Review) and older setup guides (prerequisites,
  path-commands, Supabase, Modal, env-vars, screenshots, SECURITY)
- `.env.example` annotates each key group with its stack setup doc; E2E flow
  table links setup per hop; Cisco Skill/MCP LLM procurement clarified in
  `env-vars.md`
- Screenshot gallery refreshed: CLI help includes `route`, live Modal scan
  capture updated, dashboard/skill/MCP shots retaken from Mock demo data,
  Escalated / SIE-only / pathway filter shots; regenerate UI shots with
  `scripts/capture-screenshots.mjs`

## [0.3.0] - 2026-08-05

### Added
- `cli/eslint.config.js` — flat-format ESLint 10 enforcement gate (`@eslint/js` + `globals.node`); `complexity: ['error', 10]` and `max-depth: ['error', 4]` now block in error mode at commit (eslint-cli hook) and CI (`npm run lint`), replacing the legacy `.eslintrc.cjs` for enforcement purposes
- `prototypes/dc-dashboard/eslint.config.js` — flat-format ESLint enforcement gate for the live dashboard; same rules as CLI gate plus `globals.browser`; `support.js` (generated build artifact) excluded from linting
- `pylint>=3.0` dev dependency, `[tool.pylint.similarities]` config (≥6-line similarity threshold), and `pylint-duplication` pre-commit hook (Python files only); same check wired in `static-analysis` CI job
- `scripts/pip-audit.sh` — centralised Python dep audit with documented per-CVE ignore slots
- `scripts/check_coverage_threshold_drift.py` — FE↔backend coverage threshold drift guard (self-skips when CLI has no vite config)
- `.trivyignore` — Trivy CVE suppression starter with Why/Compensating-control/Unblock format enforced per entry
- `.meterian` — Meterian SCA thresholds (security + licensing ≥95, CVSS ≥7.0); `METERIAN_API_TOKEN` already wired in CI
- `.github/PULL_REQUEST_TEMPLATE.md` — PR description template aligned with `/create-pr` skill section names (`Summary`, `Test Results`, `Checklist`, `Closes`)
- `.github/CODEOWNERS` — auto-reviewer assignment (`@neomatrix369` global fallback)
- `cli/stryker.config.mjs` — Stryker config targeting `src/**/*.js` with built-in `command` test runner, 80% kill threshold, HTML + JSON reporters
- CLI mutation testing job in `nightly.yml` (`mutation-tests-cli`) — installs only `@stryker-mutator/core@^8` (no separate test-runner package), seeds sandbox fixtures, uploads HTML/JSON report artifact (30-day retention)

### Changed
- `scripts/pre-push-gates.sh` — T3 now runs **gitleaks commit-range only** (pushed commits via `--log-opts FROM..TO`); full-tree SAST/SCA (`security-scan.sh`, semgrep, trivy, trufflehog) moved entirely to CI where latency is acceptable
- `scripts/pre-push-gates.sh` — CLI unit tests at push now gated on `CLI_CHANGED`; previously ran unconditionally on every push even when no `cli/` files were touched
- `.pre-commit-config.yaml` — added `xenon` (complexity), `vulture` (dead code), `pylint-duplication`, `eslint-cli`, and `eslint-dashboard` hooks at commit stage; all are file-type-gated so they fire only on matching changed files
- Xenon ceiling split: `scan_app.py + guard + __init__.py → --max-absolute C`; `scanners.py → --max-absolute D` (only `run_snyk` is D-grade; tracked for refactor) — clean files no longer inherit the worst offender's ceiling
- Pre-push CLI gate upgraded from bare `npm test` to `npm run test:coverage` (c8 ≥95%); the coverage floor now enforced locally before code reaches the remote, matching Python's push behaviour
- `ci.yml` `cli-tests` job: ESLint lint step added before `test:coverage`; `static-analysis` job: xenon split applied and pylint duplicate-code check added; `live-acl-tests` job: ESLint lint step added before `test:coverage`
- `.github/workflows/nightly.yml` Chalk job — replaced silent `|| true` with `continue-on-error: true` so Chalk failures appear as visible ⚠ warnings in the Actions UI rather than being swallowed
- `CLAUDE.md` — added `## PR Composition` section so agent skills include the project Checklist in generated PR bodies

### Fixed
- `prototypes/dc-dashboard/agentvetter-status.js` `normalizeSeverity` — refactored from CC 14 to CC 6 using Set-based dispatch (`SEVERITY_RED/AMBER/GREEN`); `resolveItemStatus` reduced from CC 13 to CC 8 by extracting `resolveCompletedStatus` and `resolveNoRunStatus` and removing unnecessary destructuring defaults that inflated the ESLint complexity count
- `prototypes/dc-dashboard/agentvetter-live.js` — extracted 7 named helper functions (`worstScannerSeverity`, `buildCompletedScannerSummary`, `buildScannerOutput`, `shapeScannerRow`, `resolveLastScanTime`, `getRunContext`, `shapeItem`) from the 120-line `items.map` closure; all 52 tests preserved, coverage above floors
- `cli/src/discovery.js` `discoverTargets` — refactored from CC 18 to CC 8 by extracting `resolveTarget` and `annotateWithTypes`; all 15 existing tests preserved
- `cli/src/ensureSchema.js` `applySchema` — refactored from CC 13 to CC 6 by extracting `pgSslConfig` and `pgConnectHint`; added `{ cause: err }` to preserve caught error in the chain
- `cli/src/orchestrator.js` — removed useless `contentHash = null` initialisation (always overwritten before use)
- `cli/stryker.config.mjs` — switched from non-existent `@stryker-mutator/node-test-runner` package (404 on npm) to Stryker's built-in `command` runner with `node --test test/*.test.js`; set `coverageAnalysis: "off"` (command runner limitation)
- `nightly.yml` `mutation-tests-cli` — added fixture seed step (`cp -r db fixtures cli/.stryker-tmp/`) so relative paths inside Stryker's sandbox resolve correctly and the dry-run passes without `|| true` suppression

## [0.2.0] - 2026-08-04

### Added
- Walking skeleton: CLI (`agentvetter scan`/`agentvetter setup`), schema bootstrap, Modal sandbox, fixtures, guard module, and dashboard in a single deployable slice
- Live/demo data mode — dashboard serve/sync with Supabase live data support
- `_acquire_target` dispatch for clone, copy, and introspect target modes
- Dashboard redesign with Deep Ops aesthetic and live Supabase data support
- Modal secrets sync script and sandbox deploy workflow
- Scanner console output persistence and Snyk skill CLI flag corrections
- `scan --force` and `setup --force` isolation support
- MCP discovery and Cisco scanner CLI integration
- Screenshot gallery in README: CLI output, dashboard, skills, and MCP server views
- Serious-tier project hygiene: pre-commit hooks, ruff, bandit, mypy, vulture, xenon, pip-audit, gitleaks
- Two-tier tech badges across README and docs
- Onboarding user guide with Live-first setup path and operator readiness notes

### Fixed
- Demo scan recovery: `--force` flag, rollup on failure, unreachable detail handling
- Demo heatmap stability: status SSOT, severity mapping, item upsert
- MCP fixtures: drop postponed annotations, pin Python 3.11
- Scanner detail summaries and dashboard raw_summary synthesis
- Resolve demo-blocking issues: quiet dotenv, ISO timestamps, manifest expansion
- Anon RLS policies and demo-readiness capture

### CI
- Python ship-path coverage gate at 95% (sandbox)
- CLI coverage gate at 95%
- Live ACL coverage gate at 95%
- Publish complexity evidence on pull requests
- Pinned security action versions (CodeQL v4, SBOM v0.24.0, artifact upload v7, cache v6, checkout v7, setup-python v7, setup-node v7)
- Fixed broken action pins and gitleaks permissions

### Docs
- Lean README with persona quickstart paths and early-adopter expectations
- Setup docs synced with schema bootstrap and Modal operator evidence
- Tech badges extended to docs index, quickstart, and CI workflows
- Screenshot gallery with real CLI and dashboard captures

[0.2.0]: https://github.com/neomatrix369/AgentVetter/releases/tag/v0.2.0
