# Frontline dual output contract

> Evidence state: **IMPLEMENTED** (2026-08-25, slice 28 Quality + footer delta on `main` lineage).
> Prior VERIFIED baseline: 2026-08-15 (slice 26 on Frontline branch).
> SSOT for `/av-verify`, `/av-scan`, and `/av-self-check` human + machine output
> (permanent aliases `/tw-*`; slices 27–30).

Source prompt: [`internal-docs/04_frontline/main_prompt.md`](../../internal-docs/04_frontline/main_prompt.md) § OUTPUT FORMAT.
Helpers: [`guard/verify.py`](../../guard/verify.py) (`verify_artifacts`, `format_quality_cell`).

## Audiences

Every `/av-*` (aliases `/tw-*`) status response must support two audiences with the **same** per-artifact facts:

1. **Human** — Markdown table (one row per artifact)
2. **Machine** — JSON object with an `artifacts` array

## Human Markdown table

Fixed columns (order matters):

| Name | Type | Status | Quality | Note |
|------|------|--------|---------|------|
| `example-skill` | skill | 🟢 GREEN (fresh) | 91/100 | — |

| Column | Meaning |
|--------|---------|
| **Name** | Resolved artifact name (or the unresolved query for `not-found`) |
| **Type** | `skill` / `mcp` / `tool` / `—` when unknown |
| **Status** | Display string for the six UI states (below); security-related RAG from **Cisco AI Defense** and **Snyk** |
| **Quality** | **Tessl** skill-review score as **`N/100`** (0–100, higher better) from `items.quality_score`; `—` for MCP, unscanned, scanning, not-found, or null |
| **Note** | Distinct operator hint only — do **not** repeat the shared blocked sentence here |

### Blocked footer (de-dupe)

When **any** artifact has `will_be_blocked=true`, print **once** under the table:

**Will be blocked when AgentVetter is enabled**

Do not repeat that phrase in every Note. RED / STALE / UNSCANNED / NOT FOUND / CHANGED keep distinct Note copy (threshold, remedy, locus, scan offer).

### Sources attribution

Print **once** under the table (after the blocked footer when present):

*Sources: Quality is from Tessl (Review Quality). Security-related Status (GREEN/AMBER/RED) is from Cisco AI Defense and Snyk.*

## Six UI states

| State | Display | When |
|-------|---------|------|
| `fresh` | 🟢 GREEN / 🟠 AMBER / 🔴 RED (with RAG label) | Scan result within N-day validity window |
| `stale` | ⚠️ STALE | Scan exists but older than N days (`scan_validity_days`, default 14) |
| `unscanned` | 🚫 UNSCANNED | No usable scan record (grey / missing / fail-closed error) |
| `scanning` | ⏳ SCANNING | Scan submitted, not yet complete |
| `not-found` | ❓ NOT FOUND | Name resolution returned no match |
| `red` | 🔴 RED | Supabase `heatmap_status` = `red` (`will_be_blocked`; footer carries the block warning) |

### `heatmap_status` → UI mapping

Supabase `items.heatmap_status` values observed in `guard/guard_hook.py`:
`green`, `amber`, `red`, `grey`, `error`.

| Source | Maps to UI | Notes |
|--------|------------|-------|
| `heatmap_status=green` + within N days | `fresh` with RAG `green` | Below default red threshold → approve |
| `heatmap_status=amber` + within N days | `fresh` with RAG `amber` | Blocked only when threshold is `red_and_amber` |
| `heatmap_status=red` + within N days | `fresh` with RAG `red` **and** state callout `red` | Always `will_be_blocked: true` when enforcement enabled |
| `heatmap_status=grey` or missing item | `unscanned` | Guard fails closed (`never scanned`) |
| `heatmap_status=error` | `unscanned` (fail-closed) | Treated like unscanned for enforcement |
| Scan older than N days (any RAG) | `stale` | Derived from `scanned_at` / latest completed run — **not** a heatmap enum |
| `scan_runs.status=running` (or equivalent in-flight) | `scanning` | Derived from run/batch lifecycle — **not** a heatmap enum |
| Name resolution miss | `not-found` | Skill/MCP resolution — **not** from Supabase |

`stale`, `scanning`, and `not-found` are **resolution / lifecycle** states. They are not values of `heatmap_status`.

## Machine JSON shape

```json
{
  "artifacts": [
    {
      "name": "vuln-runtime-download",
      "resolved_path": "/path/to/skill",
      "type": "skill",
      "state": "red",
      "rag": "red",
      "scanned_at": "2026-08-01T10:00:00Z",
      "stale": false,
      "will_be_blocked": true,
      "quality_score": 12,
      "note": "rated red — at/above threshold"
    }
  ]
}
```

Required per-artifact fields:

| Field | Type | Meaning |
|-------|------|---------|
| `name` | string | Display / query name |
| `resolved_path` | string \| null | Filesystem or URL path when resolved |
| `type` | string \| null | `skill` / `mcp` / `tool` |
| `state` | string | One of the six UI states |
| `rag` | string \| null | `green` / `amber` / `red` when known; null for unscanned/not-found/scanning |
| `scanned_at` | string \| null | ISO-8601 last completed scan time |
| `stale` | boolean | `true` when past N-day window |
| `will_be_blocked` | boolean | `true` when enforcement would block this artifact |
| `quality_score` | number \| null | Tessl skill-review 0–100 from `items.quality_score`; null when absent |
| `note` | string | Distinct human-facing note (no repeated blocked footer sentence) |

## Observed `agentvetter scan` JSON (introspection)

Production path: `cli/src/orchestrator.js` → `runScan` prints one JSON object to stdout.

**Observed shape (dispatch confirmation — not the dual-output artifact row):**

```json
{
  "batch_id": "<uuid>",
  "scan_run_ids": ["<uuid>", "..."],
  "failed_targets": [
    { "target": "<path-or-url>", "error": "<message>" }
  ]
}
```

| Field | Observed | Role for `/av-*` |
|-------|----------|------------------|
| `batch_id` | yes | Submit confirmation / follow-up routing |
| `scan_run_ids` | yes | Per-target run IDs when dispatch succeeded |
| `failed_targets[]` | yes | `{ target, error }` for dispatch failures |

`--dry-discover` prints the discovered **targets list** (not the `runScan` result) and exits without spawning sandboxes.

There is **no** synchronous status-lookup CLI. Per-artifact RAG / staleness for `/av-verify` (alias `/tw-verify`) comes from Supabase (`items.heatmap_status` + scan timestamps), same pattern as `guard/guard_hook.py`. Quality comes from persisted `items.quality_score` — do **not** invoke Tessl from `/av-verify`.

### BACKLOG — scan → dual-output map

| Dual-output field | From `agentvetter scan` today? | Source for skills 28–30 |
|-------------------|-----------------------------|-------------------------|
| `name` / `type` / `resolved_path` | partial (discover targets only) | Name resolution + discover |
| `state` / `rag` / `stale` / `scanned_at` | **no** | Supabase `items` + scan_runs |
| `quality_score` | **no** (persisted on `items` by sandbox Tessl) | `items.quality_score` |
| `will_be_blocked` / `note` | **no** | Guard threshold + enable flag |
| `batch_id` / `scan_run_ids` | **yes** | Echo in `/av-scan` (alias `/tw-scan`) confirmation (skill 29) |

Do not invent scan-stdout fields that are not listed above. Skills compose dual-output rows from Supabase + resolution; they use `batch_id` / `scan_run_ids` only as submit receipts.

## Links

- Skills that consume this contract: slices [27](../plan/slices/08-H-frontline-agent-hooks/slice-27-tw-enable-disable.md)–[30](../plan/slices/08-H-frontline-agent-hooks/slice-30-tw-self-check.md)
  (`/av-enable` / `/av-disable` are config toggles only — they do not emit this table;
  `/av-verify` implements the table via `guard.verify` + `agent-hooks/skills/av-verify`, slice 28)
- Operator setup / hooks: [setup-commands.md](setup-commands.md)
- Gate evidence: [`docs/plan/gate-evidence/slice-26.json`](../plan/gate-evidence/slice-26.json) ·
  [`slice-27.json`](../plan/gate-evidence/slice-27.json) ·
  [`slice-28.json`](../plan/gate-evidence/slice-28.json)
