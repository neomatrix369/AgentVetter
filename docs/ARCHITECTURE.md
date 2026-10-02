# Architecture

This page is a **map of the parts**. Skip it until you can run the
[demo Quickstart](../QUICKSTART.md#try-the-demo-recommended).

System shape for AgentVetter. Diagrams are Mermaid (text, version-controlled).

Start here: [QUICKSTART](../QUICKSTART.md) · Hub: [docs/README](./README.md) · Status: [STATUS.md](./STATUS.md)

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

## 0. External services (inventory)

Named dependencies AgentVetter uses or can use. **Setup** = create account/project;
**Configure** = keys / wiring. Local tools (Git, Node, Python, npm) are not cloud
services — see [prerequisites](./user-guide/prerequisites.md).

| Service | Role | Needed for | Setup / Configure |
|---|---|---|---|
| **Supabase** | Postgres + Realtime system of record | MVP Live | [supabase-setup](./user-guide/supabase-setup.md) → [env-vars](./user-guide/env-vars.md) |
| **Modal** | Isolated scanner sandbox compute | MVP Live | [modal-setup](./user-guide/modal-setup.md) → [env-vars](./user-guide/env-vars.md) |
| **Snyk** | Skill / MCP / package depth scanner (`applies_to: both`) | Full scanner coverage | [procurement](./user-guide/env-vars.md#vendor-procurement-quick-steps) |
| **Tessl** | Skill lint (auth-free) + review / scenario / eval / security (`TESSL_TOKEN`; `--workspace` from optional `TESSL_WORKSPACE` or `whoami`+`workspace list`) + Scenario Generation (`.tessl-plugin/plugin.json`; IMPLEMENTED unit, slice 49) + Eval auto-chain (`tessl.json` project link; IMPLEMENTED unit, slice 50) + Security Review (IMPLEMENTED unit, slice 51) | Full scanner coverage | [procurement](./user-guide/env-vars.md#vendor-procurement-quick-steps) |
| **Cisco AI Defense** | Skill Scanner / MCP Scanner / AI Defense APIs | Full scanner coverage | [procurement](./user-guide/env-vars.md#vendor-procurement-quick-steps) |
| **Superlinked SIE** | Cheap post-scan triage | Optional tiered router | [tiered-router-setup](./user-guide/tiered-router-setup.md) |
| **Alibaba Cloud Model Studio** | Escalation arbitration / triage | Optional tiered router | [tiered-router-setup](./user-guide/tiered-router-setup.md) |
| **DepShield** (`depshield-mcp`) | Local dependency-audit adapter over MCP stdio (skill, mcp_server, package) | Optional / local | No cloud account — npm package; see [STATUS](./STATUS.md) |
| **Ossprey** (`ossprey-cli`) | Malware / malicious-package scan after DepShield (skill, mcp_server, package) | Full scanner coverage (when keyed) | `OSSPREY_API_KEY` via [env-vars](./user-guide/env-vars.md) · [OPTIONAL_SCANNER_KEYS](../fixtures/OPTIONAL_SCANNER_KEYS.md); absent → `skipped_missing_credential`. IMPLEMENTED adapter; access provisioning OPEN — not VERIFIED live |
| **GitHub Actions** | CI ultra-minimal (PR/`main`) · Nightly **A** daily 02:00 (Semgrep/CodeQL/full scans) · Supply chain **B** weekly Mon 03:00 · Mutation **C** 1st+15th 04:00 · complexity · Code Review Graph nightly | Contributors | Repo secrets as needed — not operator Live; [ADR-0013](./adr/0013-ship-path-quality-gates.md) |
| **Cursor / Claude Code** | Dev tooling; Wave H agent hooks (Phase 1 on `main`) | Contributors / operators | [agent-hooks](../agent-hooks/README.md) · [frontline-output-contract](./user-guide/frontline-output-contract.md) · Wave H in [TRAIL](./plan/TRAIL.md) |

Demo / Mock path needs **no** rows above. Capability honesty: [STATUS.md](./STATUS.md).

### Operator journey (start → finish)

```mermaid
flowchart TD
  start([Clone repo]) --> demo{Want Live cloud?}
  demo -->|No — Recommended| tools[Install Node 22 + Python 3.12]
  tools --> link[npm link CLI]
  link --> dry[scan --dry-discover]
  dry --> mock[serve-dashboard Mock]
  mock --> doneDemo([Demo done])

  demo -->|Yes — Advanced| fit[Prerequisites fit check]
  fit --> setupA[A. Create accounts — Setup]
  setupA --> mvp{MVP or full scanners?}
  mvp -->|MVP| acct2[Supabase + Modal only]
  mvp -->|Full| acct5[Supabase + Modal + Snyk Tessl Cisco + optional Ossprey]
  acct2 --> keys[B. Configure keys — .env]
  acct5 --> keys
  keys --> boot[C. Bootstrap — setup + setup-modal]
  boot --> scan[agentvetter scan]
  scan --> dash[Dashboard Live]
  dash --> opt{Optional router?}
  opt -->|Yes| route[agentvetter route]
  opt -->|No| maintain
  route --> maintain[Maintain — force / secrets-only / fail table]
  maintain --> doneLive([Live ops loop])
```

### Dependency order (what before what)

```mermaid
flowchart LR
  subgraph local [Local — Demo]
    N[Node 22 + npm]
    P[Python 3.12]
    N --> CLI[agentvetter CLI]
    P --> CLI
  end

  subgraph mvp [MVP Live]
    SB[Supabase project + keys]
    MD[Modal account + tokens]
    SB --> schema[agentvetter setup]
    MD --> secrets[setup-modal.sh]
    schema --> liveScan[Live scan]
    secrets --> liveScan
  end

  subgraph scanners [Full coverage — optional]
    SK[Snyk]
    TS[Tessl]
    CS[Cisco AI Defense]
    DS[DepShield]
    OS[Ossprey]
    SK --> liveScan
    TS --> liveScan
    CS --> liveScan
    DS --> liveScan
    OS --> liveScan
  end

  subgraph router [Post-scan — optional]
    SIE[SIE]
    MS[Model Studio]
    liveScan --> SIE
    SIE --> MS
  end

  CLI -.->|Advanced only| SB
```

---

## 1. Context (C4 L1)

Who uses AgentVetter, and what it talks to (no container tech detail).

```mermaid
C4Context
  title AgentVetter — Context

  Person(user, "AgentVetter user", "Installs, runs scans, and reviews findings")
  System(agentvetter, "AgentVetter", "Discovers skills/MCP targets, runs scanners, stores results")
  System_Ext(scanners, "Upstream scanners", "Skill/MCP/SCA analysis tools")
  System_Ext(cloudDb, "Hosted database", "Stores scan runs and findings")
  System_Ext(compute, "Serverless compute", "Isolated scanner execution")
  System_Ext(sie, "SIE / Model Studio", "Optional post-scan triage and escalation")

  Rel(user, agentvetter, "1. Invokes scan / setup / route")
  Rel(agentvetter, compute, "2. Spawns scan jobs")
  Rel(compute, scanners, "3. Runs scanner CLIs")
  Rel(agentvetter, cloudDb, "4. Reads/writes scan data")
  Rel(compute, cloudDb, "5. Writes findings")
  Rel(agentvetter, sie, "6. Optional tiered route")
```

---

## 2. Containers (C4 L2)

Deployable / runnable units inside the system boundary.

```mermaid
C4Container
  title AgentVetter — Containers

  Person(user, "AgentVetter user")

  System_Boundary(av, "AgentVetter") {
    Container(cli, "CLI", "Node.js", "Discovery, hashing, idempotency, Modal spawn, tiered route")
    Container(sandbox, "Sandbox app", "Python / Modal", "Acquire target, run adapters")
    ContainerDb(db, "Database", "Postgres / Supabase", "schema.sql, Realtime")
    Container(dash, "Dashboard", "HTML / JS", "Live/Mock UI; Dashboard inventory tab + Workflow Run→Report; pathway strips; Escalated / SIE-only filters")
  }

  System_Ext(scanners, "Upstream scanners")
  System_Ext(sie, "SIE / Model Studio")

  Rel(user, cli, "1. agentvetter scan / setup / route")
  Rel(user, dash, "2. Views Live, dry-discover, or demo results")
  Rel(cli, db, "3. Bootstrap + scan_run rows")
  Rel(cli, sandbox, "4. Spawn scan")
  Rel(sandbox, scanners, "5. Shell out")
  Rel(sandbox, db, "6. Findings / console")
  Rel(cli, sie, "7. Optional post-scan route")
  Rel(cli, db, "8. tiered_router findings")
  Rel(dash, db, "9. Realtime or poll")
```

### Repo layout (where containers live)

- `cli/` — `agentvetter` Node CLI (`scan`, `setup`, `route`; `tripwire` shim)
- `sandbox/` — Modal app + scanner adapters (`scanners.py`); unit tests in `sandbox/tests/`
- `db/schema.sql` — Postgres/Supabase DDL + rollup + `dashboard_latest_runs` view
  (Live dashboard: one latest `scan_run` per item); anon SELECT + Realtime
- `prototypes/dc-dashboard/` — Live/Mock dashboard (Horizon A ship UI; prototype path). Public Mock preview: [neomatrix369.github.io/demos/agentvetter-dashboard/](https://neomatrix369.github.io/demos/agentvetter-dashboard/) · [demo video](https://youtu.be/omGOw9ruN3Y). Shows router pathway strips (`Scan → ■` / `Scan → SIE → ■` / `Scan → SIE → Model Studio`), Escalated / SIE-only filters, and skill quality triage tabs (**Quality ≥ 80** / **Quality < 80** / **No quality score** — slice 42 A14–A15 ON BRANCH) — [reading-router-results.md](./user-guide/reading-router-results.md)
- `prototypes/sie-studio/` / `prototypes/model-studio/` — sample CLIs for router backends
- `scripts/` — setup (Supabase/Modal), `serve-dashboard.mjs`, hygiene gates, router fixtures
- `fixtures/` — smoke targets — [fixtures/README.md](../fixtures/README.md)
- `docs/research/adapters/scanner-output-adapters.md` — keep in sync with `sandbox/scanners.py`

### Scanner timeout budget

Scanners in `run_all_scanners` run **sequentially**. Each adapter passes an
individual `timeout=` to `_run`; `SCAN_TIMEOUT` (240s) is the per-call ceiling.
Modal hard-kills the sandbox at `TIMEOUT_SECONDS` (300s in `scan_app.py`).

| Constant | Value | Role |
| -------- | ----- | ---- |
| `SCAN_TIMEOUT` | 240s | Default per-scanner subprocess cap |
| `DEPSHIELD_TIMEOUT` | 120s | DepShield MCP stdio client |
| `OSSPREY_TIMEOUT` | 100s | Ossprey malware scan (tail group) |

CI enforces `DEPSHIELD_TIMEOUT + OSSPREY_TIMEOUT <= SCAN_TIMEOUT` via
[`scripts/check-scanner-timeout-budget.sh`](../scripts/check-scanner-timeout-budget.sh).
Earlier groups (Skill, Tessl, MCP, Snyk) must finish within the remaining wall
clock before Modal's 300s kill — operators reconcile stranded `running` rows with
[`scripts/reconcile-stuck-scan-runs.mjs`](../scripts/reconcile-stuck-scan-runs.mjs).

### Future (not current Horizon A containers)

- `guard/` — PreToolUse-style Agent Guard hook. **Horizon A:** Won't / not a
  shipped production entry ([ADR-0015](./adr/0015-horizon-a-excludes-guard-and-drift.md)).
  **Wave H (Frontline):** Phase 1 hooks + `agentvetter setup-agent-hooks` + `/av-*` (aliases `/tw-*`)
  skills live under [agent-hooks](../agent-hooks/README.md) on `main`. Slice 28
  (`/av-verify` Quality `N/100` + blocked footer + Sources attribution; alias `/tw-verify`) is
  **IMPLEMENTED** on `slice/28-tw-verify-quality` — dual-output SSOT
  [frontline-output-contract.md](./user-guide/frontline-output-contract.md)
  (Quality = Tessl; Status = Cisco AI Defense + Snyk).
  Formal Wave H gate trackers (23–27, 29–32) still lag — see [STATUS.md](./STATUS.md)
  and [plan/TRAIL.md](./plan/TRAIL.md) Wave H.
- **Wave M (LLM usage / cost observability, DECIDED plan-only):** slice 53
  intends append-only `llm_usage_events`, a dashboard Usage tab with a
  collapsible historic transaction log, cost tips on router chrome, and
  `agentvetter usage`. Design:
  [design/llm-usage-tracking.md](./design/llm-usage-tracking.md) ·
  [plan/TRAIL.md](./plan/TRAIL.md) Wave 13-M. **Not IMPLEMENTED** — router still
  discards provider `usage`; no Usage tab. See [STATUS.md](./STATUS.md).
- **Wave O (Monk Kit Live packaging, DECIDED plan-only / ADR-0001 Proposed):**
  intended path is a Monk Kit (in-cluster bootstrap + dashboard + HTTPS ingress;
  Supabase/Modal/scanners as SaaS). **O0** + slices 58–61 in
  [plan/TRAIL.md](./plan/TRAIL.md) Wave 15-O. **Not IMPLEMENTED** — no Kit
  artifacts on `main`; workstation Live remains the supported path. See
  [ADR-0001](./adr/0001-monk-deployment-and-packaging.md) · [STATUS.md](./STATUS.md).
- **Wave P (Git repo discover + fan-out, slices 62–64 ✅ on `main`):** GitHub
  browse URLs (`/tree/…`, `/blob/…`) normalize to cloneable repo root; host
  discover of skills **and** MCPs fans out to N separate Modal scans (scanners
  by `item_type`); dashboard cards titled by skill/MCP name + `org/repo`
  signatures (`identifier` `org/repo/<relpath>`); re-scan refreshes `items.name`
  even when content hash matches (spawn still skipped unless `--force`).
  **Slice 64:** package manifests at scope root also emit one `items.type=package`
  target (Snyk `snyk test` SCA / DepShield / Ossprey only — not Cisco Skill /
  Tessl / Cisco MCP). Cargo-only trees: unsupported engines → `not_applicable`;
  complete runs with zero completed engines → **UNSCANNED** (grey), not green.
  **Slice 63:** CLI prints `[scanners]` inventory + rollup after scan / zero-artifact.
  Repos with neither skill/MCP **nor** package manifests fail closed. Spec:
  [slice 62](./plan/slices/16-P-git-repo-scan/slice-62-git-repo-discover-fanout.md) ·
  [slice 63](./plan/slices/16-P-git-repo-scan/slice-63-cli-scanner-inventory.md) ·
  [slice 64](./plan/slices/16-P-git-repo-scan/slice-64-git-repo-package-scan.md) ·
  [plan/TRAIL.md](./plan/TRAIL.md) Wave 16-P. Operator taxonomy:
  [prerequisites — What can AgentVetter scan?](./user-guide/prerequisites.md#what-can-agentvetter-scan). See
  [STATUS.md](./STATUS.md).

---

## 3. Key Flows

### Dry-discover (no Modal)

```mermaid
sequenceDiagram
  autonumber
  participant Op as Operator
  participant CLI as agentvetter CLI

  Op->>CLI: agentvetter scan --dry-discover path
  CLI-->>Op: Print discovered targets
  CLI-->>Op: Print [coverage] / [evidence] honesty rows when applicable
  Note over CLI: Exits without spawning sandbox
```

### Full scan (Supabase + Modal + dashboard)

```mermaid
sequenceDiagram
  autonumber
  participant Op as Operator
  participant CLI as agentvetter CLI
  participant SB as Modal sandbox
  participant DB as Supabase
  participant Route as SIE / Model Studio
  participant Dash as Dashboard

  Op->>CLI: agentvetter scan path
  CLI->>DB: Ensure schema / create scan_run
  CLI->>SB: Spawn scanners
  SB->>DB: Findings / console_output
  CLI-->>Op: Scanner inventory + rollup (slice 63)
  CLI->>Route: Auto-route batch (optional; warn+skip if keys missing)
  Route-->>CLI: Triage / escalation
  CLI->>DB: tiered_router findings
  Dash->>DB: Realtime or poll
  Dash-->>Op: Live results UI
```

Manual re-route: `agentvetter route --batch-id …` ([setup-commands.md](./user-guide/setup-commands.md#tiered-router-optional)).

### Tiered routing

Multi-scanner batches can disagree on severity, leave unusual scanner statuses
(timeout / unreachable), or produce low-confidence finding text. Operators need a
post-scan signal separate from raw scanner rows.

1. **SIE** (cheap / every item) decides whether to escalate using pre-computed
   `conflicting` + `unusual_status` plus its own `low_confidence` judgment.
2. **Model Studio** (stronger / escalate only) runs either **arbitration**
   (findings present) or **triage** (empty findings + coverage gap).
3. Persist one `tiered_router` finding per item (`routing_review` /
   `routing_decision` / `routing_triage`). Replace that item's prior router row
   only after a successful SIE decision — never batch-delete first.
4. Dashboard surfaces pathway strips and Escalated / SIE-only filters
   ([reading-router-results.md](./user-guide/reading-router-results.md)).

Missing SIE credentials → warn and skip (scan unaffected). See
[ADR-0016](./adr/0016-tiered-router-sie-model-studio.md).

### Quality attributes — severity rollup

`agentvetter_rollup_item` aggregates **scanner** findings only. Rows with
`scanner_source = 'tiered_router'` are excluded so triage does not inflate
red/amber counts or `risk_score`. Card `heatmap_status` is worst-of actionable
scanner severities when ≥1 engine **completed**; finding-count chips are density,
not colour ([ADR-0004](./adr/0004-supabase-system-of-record.md),
[ADR-0016](./adr/0016-tiered-router-sie-model-studio.md)).

**Zero completed engines:** a `complete` run where every applicable scanner is
`not_applicable` / skipped (e.g. Cargo-only package targets — DepShield npm/PyPI
only, Ossprey Python/JS only, `snyk test` without Rust) rolls up to
`heatmap_status=grey` (UNSCANNED) with `risk_score` null — never a false green.
A `partial-failed` run with zero completed engines still rolls up to `error`.
Live dashboard `resolveItemStatus` mirrors this when `completedScannerCount === 0`.

`risk_score` (sort/trend only) =

`(3 × red_findings + 1 × amber_findings) / Σ checks_run` on completed scanners
for the latest run. Range ≥ 0 and unbounded; `null` when unscored (including
all-N/A complete). Dashboard card colour must not be inferred from this number
alone.

`quality_score` is the Tessl skill-review axis (0–100, higher better), written
by `run_tessl` / `_tessl_quality_score` and mapped into Live as `item.quality`
on the `"Tessl: Review (Quality)"` scanner row only. `"Tessl: Lint"` is a
separate `scan_run_scanners` row (slice 46 ✅ persist scan_run `a36cad9f`):
`tessl skill lint`, auth-free, no `tessl_run_id`. Review Quality (slice 47 ✅
[#109](https://github.com/neomatrix369/AgentVetter/pull/109))
uses `tessl review run quality --json --workspace` and stamps `tessl_run_id`
from `tessl review view --last --json`, then seeds in-process
`_TesslIdContext["review_quality"]` for slices 49–51 (GWT-47.5). It is orthogonal to findings and to `risk_score`. **IMPLEMENTED (UI):** slice 48 synthesises "Not Available Yet" sentinel rows for Tessl capabilities absent from the scan_run (never stored as placeholders). **IMPLEMENTED (unit, slice 49):** Scenario Generation writes a real `scan_run_scanners` row (`scenario generate` → `download` into `<plugin>/evals/`, `resume_checkpoint`, mid-scan persist). **IMPLEMENTED:** Tessl dashboard progress — `scan_app` skips bulk `running` placeholders for the Tessl group; `run_tessl` persists Lint and Review (Quality) step-by-step via `on_scanner_progress` (not only at group end). **IMPLEMENTED (unit, slice 50):** Eval starts `blocked`, auto-chains after Scenario Gen when `evals/` is populated (`eval run --runs 3 -y` + `eval view`; stale on scenario re-run; project create/repair preflight). **IMPLEMENTED (unit, slice 51):** Security Review writes `"Tessl: Review (Security)"` via `_run_tessl_review("security")` after Eval; `upstream_run_ids.review_quality` is attached before invoke; expanded Security row shows linked Quality findings when that ID is populated — see
[design/tessl-5-row-expansion.md](./design/tessl-5-row-expansion.md) and slices
49–51; scenario→eval pipeline is generate → download → `eval run` on disk
`evals/` (sandbox-populated; host `evals/` is not a vuln-scan input — packing
exclude **VERIFIED** in slice 48 ✅ [#110](https://github.com/neomatrix369/AgentVetter/pull/110): Tessl plugin pack/copy omits root `evals/`;
git clone / `hashLocalPath` unchanged). Dashboard skill cards surface
compact `Q N` / `Q —` / `Q ?` badges with a fixed `#score-tip-portal` (not delayed
native `title=`, not in-card absolute bubbles that clip under `overflow-y: auto`);
risk uses compact `R N.NN` badges (list header **Risk density**) with the same
portal tip pattern — slice 42 A9–A13 IMPLEMENTED ([PR #98](https://github.com/neomatrix369/AgentVetter/pull/98));
operator chrome uses plain labels
(`Tessl quality`, locus/avail glossary) rather than schema snake_case.

Public docs map services and Setup→Maintain order in
[§0 External services](#0-external-services-inventory) (slice 44 GWT-44.8, ON BRANCH).

---

## 4. Component Detail (C4 L3)

Omitted — container internals are readable from `cli/`, `sandbox/`, and
`prototypes/dc-dashboard/`. Add L3 only when a container becomes hard to navigate
from the code.

---

## 5. Decisions

- Formal ADRs: [adr/README.md](./adr/README.md)
- Planning decisions (slice waivers, priority): [plan/DECISIONS.md](./plan/DECISIONS.md)
- Slice progress: [plan/PROGRESS.md](./plan/PROGRESS.md)
