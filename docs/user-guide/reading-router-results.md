# Reading tiered router results

> How to interpret pathway strips, Escalated / SIE-only filters, and
> `tiered_router` finding categories after optional post-scan routing
> ([ADR-0016](../adr/0016-tiered-router-sie-model-studio.md)).

Start here: [QUICKSTART](../../QUICKSTART.md) · Setup:
[tiered-router-setup.md](./tiered-router-setup.md) ·
[setup-commands.md § Tiered router](./setup-commands.md#tiered-router-optional).

## Plain words (glossary)

| Term | Plain meaning |
|---|---|
| **Mock** | Demo dashboard data — no cloud accounts, not a real scan |
| **Live** | Real scan results stored in Supabase |
| **Heatmap / card colour** | Worst scanner severity (red / amber / green) — not the same as risk density |
| **Risk density** | Sort/trend number from finding counts; not the card colour |
| **Tessl quality** | Tessl quality review score (0–100) from `tessl review run quality`, shown as `Q` on Live cards — not risk. Same axis as `/av-verify` **Quality** (`N/100` from `items.quality_score`; alias `/tw-verify`). On `/av-verify`, **Status** (GREEN/AMBER/RED) is the security rollup from Cisco AI Defense and Snyk — see [frontline-output-contract.md](./frontline-output-contract.md) Sources line |
| **Pathway strip** | Short path drawn on a card: Scan → SIE → Model Studio |
| **Escalated** | Model Studio actually ran (arbitration or triage) |
| **SIE-only** | SIE reviewed; Model Studio did **not** run |
| **tiered_router** | Informational triage row — not a fourth scanner; excluded from risk rollup |

## Dashboard vs Workflow tabs

The Live/Mock UI has two primary tabs:

| Tab | What it is for |
|---|---|
| **Dashboard** (default) | Inventory heatmap, KPIs, filters, cards, pathway strips, Escalated / SIE-only |
| **Workflow** | Run → Triage → Investigate → Fix → Verify → Report stepper for an approved-repo guided path |

Simple/Expert on Workflow only changes finding-detail density. Operator-visible
judge/coverage/evidence-verify narration **and** L→R soft-amend (parent meta,
multi-select, role-labelled models) are **IMPLEMENTED / VERIFIED** (unit) on
`main` via Wave R slice 75
([PR #163](https://github.com/neomatrix369/AgentVetter/pull/163)); denser Triage
filters + shared panel typography via slice 76
([PR #165](https://github.com/neomatrix369/AgentVetter/pull/165)) — see
[STATUS.md](../STATUS.md). Optional `AGENTVETTER_JUDGE_PANEL=1` enables the CLI
panel ([env-vars.md](./env-vars.md)).

## What you are looking at

After a batch is routed, each processed item has one finding with
`scanner_source = tiered_router`. That row is **informational triage**, not a
fourth scanner engine: it does not inflate heatmap risk scores (rollup excludes
`tiered_router`). Card colour still comes from scanner findings — **worst
actionable severity** (any red → red; amber-only → amber; else green when
scanners completed cleanly). A finding-count chip is density, not colour.

## Pathway strips (always visible on the card)

| Strip | Meaning |
|---|---|
| `Scan → ■` | SIE was never called for this item (keys missing / soft-skip). Prior strip preserved when re-route skips. |
| `Scan → SIE → ■` | SIE reviewed the item and **did not** escalate to Model Studio |
| `Scan → SIE → Model Studio` | SIE escalated; Model Studio ran arbitration or triage |

Open the finding tooltip for model IDs (`SIE=…` · `MS=…` or `—`), signal flags,
and the claim label below.

## Filter chips

| Chip | Matches | Use when |
|---|---|---|
| **Escalated** | `routing_decision` or `routing_triage` | Model Studio actually ran |
| **SIE-only** | `routing_review` | SIE ran; Model Studio did **not** |

Severity chips (red / amber / green) still filter by heatmap severity. Escalated
and SIE-only are independent of colour.

## Categories and severity meaning

Same `severity` column, different meaning by `category`:

| Category | Claim label in UI | `severity` means |
|---|---|---|
| `routing_review` | **SIE only — not escalated** (and/or **No Model Studio call**) | Vulnerability-style rollup severity for the item (or soft-fail / skip note) |
| `routing_decision` | **Arbitration:** | Arbitrated vulnerability severity when scanners disagreed or confidence was low |
| `routing_triage` | **Triage urgency:** | Coverage-gap **urgency** (re-scan priority) — not a vuln verdict |

## Soft-fail behaviour

- **Missing SIE keys** → scan still succeeds; auto-route / `agentvetter route` warns
  and skips. No new router rows for those items.
- **SIE keys present, Model Studio keys missing** → SIE can still write
  `routing_review` rows; escalation paths that need Model Studio soft-fail into a
  review row with a failure note when appropriate.
- **SIE outage on re-run** → replace-on-success only: prior strips are not
  batch-deleted before the run.

## Preview without a Live route

1. Mock dashboard already includes `tiered_router` fixtures — open
   [http://127.0.0.1:8765/AgentVetter.dc.html](http://127.0.0.1:8765/AgentVetter.dc.html)
   with `node scripts/serve-dashboard.mjs` and toggle **Escalated** / **SIE-only**.
2. Gallery shots: [screenshots README](../screenshots/README.md)
   (dashboard router filters + Workflow Run/Triage/Verify).
3. Live conflict / timeout fixtures (needs Supabase `.env`):

```bash
node scripts/seed-router-fixtures.js
```

Prerequisites: `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` (same as Live scans).
The script upserts fixture items (`Conflict Test Skill`, timeout-style coverage
gaps), scanner rows, and findings so you can exercise Live UI without waiting for
a real multi-scanner disagreement. Re-open the dashboard in **Live** mode after
seeding.

## Manual re-route

```bash
agentvetter route --batch-id <batch_id>
# agentvetter route --batch-id <batch_id> --sie-model gen-4b --model-studio-model qwen3.8-max
```

See [setup-commands.md](./setup-commands.md#tiered-router-optional) for the key
matrix and flags.

## Related

- Design rationale: [ADR-0016](../adr/0016-tiered-router-sie-model-studio.md)
- Architecture flow: [ARCHITECTURE.md](../ARCHITECTURE.md#tiered-routing)
- Sample CLIs (iterate without a full scan): [prototypes/sie-studio](../../prototypes/sie-studio/README.md),
  [prototypes/model-studio](../../prototypes/model-studio/README.md)
- **Future (DECIDED plan-only):** LLM usage / cost metering and a dashboard Usage
  tab — [llm-usage-tracking.md](../design/llm-usage-tracking.md). Not shipped yet;
  router still discards provider `usage`.
