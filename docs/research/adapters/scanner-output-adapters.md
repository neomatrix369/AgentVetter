# Scanner output → Tripwire findings adapters (research)

**Status:** RESEARCH (in progress — schemas inventoried from primary docs; fixture VERIFIED maps still open)
**Started:** 2026-08-01
**Purpose:** Document how each scanner emits results, how to capture them, proposed maps into Supabase (`findings` + Storage), and **cited references**.

**Product SoT:** private references §4 · §8
**Trusted domains:** [`.nwave/trusted-source-domains.yaml`](../../../.nwave/trusted-source-domains.yaml)
**Also mirrored for nWave layout:** `docs/research/adapters/` (symlink or copy of this file when finalized)

Evidence labels: **RESEARCH** | **PROPOSED** | **DECIDED** | **VERIFIED**

---

## 0. Dual-write contract (DECIDED — product spec)

| Path | Destination | Role |
|---|---|---|
| A — Raw | Supabase Storage (3 buckets) | Native engine output + logs + optional source |
| B — Normalized | Postgres `findings` (+ `scan_run_scanners`) | Shared severity / category / anchors |
| C — Quality | `items.quality_score` | Tessl only |

Adapters always: upload raw blob → emit `Finding[]` → write `scan_run_scanners` row.

---

## 1. Cross-cutting severity collapse (PROPOSED)

| Upstream | Tripwire `severity` |
|---|---|
| CRITICAL, HIGH, `E*` (Snyk) | `red` |
| MEDIUM, LOW, most `W*` (Snyk) | `amber` |
| INFO | `green` (soft / informational only — does not raise card risk) |
| SAFE / empty issues | no finding row |

Finalize after fixture smokes.

---

## 2. Snyk Agent Scan (`snyk-agent-scan`)

### Capture (RESEARCH — from official JSON doc)

```bash
uvx snyk-agent-scan@latest --json <path>
uvx snyk-agent-scan@latest --ci --dangerously-run-mcp-servers --json <path>
```

- `--json` → **stdout is JSON only** (banner suppressed); debug on stderr with `--verbose`.
- **Pin package version** in Modal image: upstream marks CLI output **experimental** (field names / codes may change).

### Output shape (RESEARCH)

Root = map `absolute_path → ScanPathResult`:

| Field | Type | Use |
|---|---|---|
| `client` | string\|null | Agent client label |
| `path` | string | Scan path |
| `error` | ScanError\|null | Path-level failure → `scan_run_scanners` unreachable / failed |
| `servers` | array\|null | MCP servers **or** skills |
| `issues` | Issue[] | Real findings (`E*` / `W*`) — **not** `labels` (deprecated) |
| `labels` | array | **Ignore** |

**Issue:**

| Field | Map to Tripwire |
|---|---|
| `code` | → `category` via lookup (E004→`prompt_injection`, W008→`hardcoded_secrets`, …) |
| `message` | → `message` |
| `reference` | `[server_index, entity_index]` → resolve skill file **or** MCP tool/prompt for anchors |
| `extra_data` | → optional `snippet` / advisory fields if present |

**Severity:** `E*` → red; `W*` → amber (tune per code at VERIFIED).
**Runtime failures:** `X*` / `error.is_failure` → engine status, not security findings.

**Anchors (PROPOSED):**

- Skill: Anchor A from `servers[i].server.path` (type `skill`) + entity file when `entity_index` set
- MCP: Anchor B from signature tools/prompts when `entity_index` set; whole-server when `entity_index` is null

### References

| Source | URL | Access | Reputation | Status |
|---|---|---|---|---|
| JSON output schema | https://github.com/snyk/agent-scan/blob/main/docs/json-output.md | 2026-08-01 | high | fetched (raw) |
| Issue codes | https://github.com/snyk/agent-scan/blob/main/docs/issue-codes.md | 2026-08-01 | high | fetched (partial) |
| Scanning | https://github.com/snyk/agent-scan/blob/main/docs/scanning.md | 2026-08-01 | high | Exa |
| README stability notice | https://github.com/snyk/agent-scan | 2026-08-01 | high | Exa |
| PyPI | https://pypi.org/project/snyk-agent-scan/ | 2026-08-01 | high | Exa |

**Open:** Full E*/W* → Tripwire category table; golden `--json` from fixtures.

---

## 3. Cisco Skill Scanner (`skill-scanner`)

Upstream tool Tripwire wraps; product CLI is `tripwire`.

### Capture (RESEARCH)

```bash
skill-scanner scan ./path/to/skill --format json --output results.json
# optional: --compact ; deepeners --use-behavioral --use-llm --use-aidefense
```

Prefer **JSON** for adapters; optionally also keep **SARIF** blob in Storage for audit.

### Output shape (RESEARCH — sample from official output-formats.md)

Top-level: `skill_name`, `skill_path`, `is_safe`, `max_severity`, `findings_count`, `findings[]`, `analyzers_used`, `scan_metadata`, …

**Finding object (high fidelity for Tripwire):**

| Upstream field | Tripwire column | Confidence |
|---|---|---|
| `severity` (CRITICAL/HIGH/…) | `severity` via collapse table | high |
| `category` (e.g. `data_exfiltration`) | `category` (map snake_case → taxonomy) | high |
| `title` + `description` | `message` | high |
| `file_path` | Anchor A `file_path` | high |
| `line_number` | Anchor A `location` | high |
| `snippet` | `snippet` | high |
| `analyzer` | contribute to `scanner_source` e.g. `Cisco: static` | high |
| `metadata.aitech` / `aitech_name` | advisory / taxonomy crosswalk | medium |
| `rule_id` | store in message or future column | medium |
| `remediation` | append to `message` or Storage-only | low |

### References

| Source | URL | Access | Reputation | Status |
|---|---|---|---|---|
| Output formats + JSON sample | https://github.com/cisco-ai-defense/skill-scanner/blob/main/docs/reference/output-formats.md | 2026-08-01 | high | fetched (raw) |
| Integrations format table | https://github.com/cisco-ai-defense/skill-scanner/blob/main/docs/development/integrations.md | 2026-08-01 | high | Exa |
| CLI reference | https://github.com/cisco-ai-defense/skill-scanner/blob/main/docs/reference/cli-command-reference.md | 2026-08-01 | high | Exa |
| Meta-analyzer finding shape | https://github.com/cisco-ai-defense/skill-scanner/blob/main/docs/architecture/analyzers/meta-analyzer.md | 2026-08-01 | high | Context7 |
| Context7 lib | `/cisco-ai-defense/skill-scanner` | 2026-08-01 | medium | indexed |
| README | https://github.com/cisco-ai-defense/skill-scanner | 2026-08-01 | high | Exa |

**Open:** Category string → Tripwire taxonomy map; per-analyzer `scanner_source` naming convention.

---

## 4. Cisco MCP Scanner (`mcp-scanner`)

Upstream tool Tripwire wraps; product CLI is `tripwire`.

### Capture (RESEARCH — prefer enveloped JSON)

```bash
# Recommended for adapters (envelope)
mcp-scanner --format raw … > out.json

# Bare array (no envelope) — OK for jq, weaker for provenance
mcp-scanner --raw … > out.json
```

| Flag | Envelope | Use |
|---|---|---|
| `--format raw` | `{ server_url, scan_results, requested_analyzers }` | **CI / adapters** |
| `--raw` / `-r` | bare array of results | quick inspection |

**Version drift:** Current docs use global flags before mode (`remote`, `behavioral`, …). Spec §8 still describes older `config` / `vulnerable-package` / `behavioral` subcommands from a prior validation pass — **reconcile against the pinned PyPI version before coding.**

Product note that file `--output` was flaky on a tested build: re-test on pin; prefer stdout redirect either way.

### Output shape (RESEARCH — official JSON schema)

**Envelope:** `server_url`, `scan_results[]`, `requested_analyzers[]` (`api`, `yara`, `llm`, `behavioral`, `readiness`, …).

**Each scan result:** `status`, `is_safe`, `item_type` (`tool`\|`prompt`\|`resource`), `findings` object, plus type fields (`tool_name`, `prompt_name`, `resource_uri`, …).

**Per-analyzer entry** (keys like `yara_analyzer`, `llm_analyzer`, `api_analyzer`, …):

| Field | Map to Tripwire |
|---|---|
| `severity` HIGH/MEDIUM/LOW/SAFE | collapse → `severity`; skip SAFE |
| `threat_names[]` | seed `category` / message |
| `threat_summary` | `message` |
| `mcp_taxonomies[]` | `scanner_category`, `aitech`, `aisubtech` → taxonomy crosswalk |
| analyzer key | `scanner_source` (`Cisco: YARA`, `Cisco: LLM-judge`, `Cisco: AI Defense API`, …) |

**Anchors (PROPOSED):**

- Live introspect: Anchor B — `entity_kind` from `item_type`, `entity_name` from `tool_name` / `prompt_name` / `resource_name`
- Behavioral source tier: Anchor A when file/line present (confirm on behavioral docs + samples)

### References

| Source | URL | Access | Reputation | Status |
|---|---|---|---|---|
| Output formats + full JSON schema | https://github.com/cisco-ai-defense/mcp-scanner/blob/main/docs/output-formats.md | 2026-08-01 | high | fetched (raw) |
| Behavioral scanning | https://github.com/cisco-ai-defense/mcp-scanner/blob/main/docs/behavioral-scanning.md | 2026-08-01 | high | Exa |
| Programmatic usage | https://github.com/cisco-ai-defense/mcp-scanner/blob/main/docs/programmatic-usage.md | 2026-08-01 | high | Exa |
| MCP threats taxonomy | https://github.com/cisco-ai-defense/mcp-scanner/blob/main/docs/mcp-threats-taxonomy.md | 2026-08-01 | high | linked from output-formats |
| API reference | https://github.com/cisco-ai-defense/mcp-scanner/blob/main/docs/api-reference.md | 2026-08-01 | high | Exa |
| PyPI | https://pypi.org/project/cisco-ai-mcp-scanner/ | 2026-08-01 | high | Exa (noted v4.7.1) |
| AI Defense | https://developer.cisco.com/docs/ai-defense/ | 2026-08-01 | high | product §8 |

**Open:** Pin version + CLI reconciliation; vulnerable-package / SCA field paths; golden fixture JSON.

---

## 5. Tessl

| Item | Status |
|---|---|
| Target | DECIDED — `items.quality_score` only (Review Quality row; Lint / Scenario Generation / Eval / Review Security do not write this axis) |
| Capture | IMPLEMENTED (slice 47) — `tessl review run quality --json --workspace`; run ID via `review view --last --json` (fallback: run JSON `id`/`runId`/`run_id`). Requires `TESSL_TOKEN` + `TESSL_WORKSPACE`. |
| Scenario Generation | IMPLEMENTED unit (slice 49) — separate `scan_run_scanners` row; plugin-path `scenario generate` / `download` into `<plugin>/evals/`; no `quality_score` write |
| Eval | IMPLEMENTED unit (slice 50) — `"Tessl: Eval"` row starts `blocked`, auto-chains after Scenario Gen when `evals/` is non-empty; `eval run --runs 3 -y --json` + `eval view`; `upstream_run_ids`; project create/repair; stale on scenario re-run; no `quality_score` write |
| Review (Security) | IMPLEMENTED unit (slice 51) — `"Tessl: Review (Security)"` after Eval via `_run_tessl_review("security")`; `upstream_run_ids.review_quality` before invoke; Security `tessl_run_id` via `review view --last`; no `quality_score` write |
| Raw | Store JSON in Storage for audit |

### References

| Source | URL | Access | Reputation | Status |
|---|---|---|---|---|
| Tessl docs | https://docs.tessl.io | 2026-08-01 | high | not yet deep-fetched |
| Product spec §8 | local | 2026-08-01 | SoT | — |

---

## 6. Sandbox denied-egress (first-party)

DECIDED in product Phase 2: allowlist deny → `findings` with sandbox `scanner_source`, `category` = `undeclared_egress_attempt`. No third-party doc required.

---

## 7. DepShield (`depshield-mcp`)

Zero-credential dependency auditor (npm + PyPI via OSV.dev). Runs for **both**
item types; group appended **last** in the `SCANNER_GROUPS` registry
(`sandbox/scanners.py`). Not Sonatype DepShield (GitHub-app-only, discontinued
2022) — see [DECISIONS.md](../../plan/DECISIONS.md) 2026-08-15.

### Capture (VERIFIED — live run of `depshield-mcp` v1.0.0, serverInfo 0.1.0, 2026-08-15)

Unlike the other adapters (subprocess CLI + JSON), DepShield is driven over
**MCP stdio** with newline-delimited JSON-RPC:

```
initialize  {protocolVersion: "2024-11-05", …}
  → notifications/initialized
  → tools/call audit_project {filePath: <manifest>, includeDevDependencies: true}
```

`<manifest>` is the discovered `package.json` / `requirements.txt` in the
workdir. The package is baked into the Modal image; no keys, no
`skipped_missing_credential` path.

### Output shape (VERIFIED — same live run)

The tool result is a **human-readable report text**, not structured JSON.
Parse anchors:

| Anchor | Use |
|---|---|
| `Summary: N dependencies scanned` | `checks_run` for the `scan_run_scanners` row |
| `📦 name@version` block | one vulnerable dependency; seeds `message` prefix |
| `• ID (SEVERITY): summary` bullet | one finding row per bullet (ID = OSV/GHSA/CVE) |

**Severity collapse:** CRITICAL/HIGH → `red`; MEDIUM/LOW → `amber`;
UNKNOWN → `amber` (conservative — OSV entries without a severity score must
not vanish). No INFO tier is emitted, so the cross-cutting `green` row does
not apply.

Raw report text goes to Storage per the §0 dual-write contract.

### References

| Source | URL | Access | Reputation | Status |
|---|---|---|---|---|
| npm package | https://www.npmjs.com/package/depshield-mcp | 2026-08-15 | high (maintainer-owned OSS) | live-run verified |
| OSV.dev API | https://osv.dev | 2026-08-15 | high | upstream data source |

**Evidence note:** this entry is labeled **VERIFIED** against a live
MCP-stdio run of `depshield-mcp` v1.0.0 (serverInfo 0.1.0) on 2026-08-15 —
the invocation sequence and parse anchors above were observed, not inferred
from docs. That is the same research-vs-verified discipline the other
sections follow: they stay RESEARCH/PROPOSED until their fixture smokes land.

**Open:** golden report-text fixture under `fixtures/scanner-samples/depshield/`;
re-verify anchors on version bump (report text is not a stable API).

---

## 8. Ossprey (`ossprey-adapter`)

Open-source **malware / malicious-code** detector (static + behavioural signals
over manifests and lockfiles) from [ossprey.com](https://ossprey.com) (GitHub org
`OSSPREY`), CLI `ossprey-cli` (Go). This is **not** CVE/SCA — it answers "does
this package tree contain malware?", complementary to and distinct from §7
DepShield's dependency-CVE audit. Registered **after** DepShield in
`SCANNER_GROUPS` (`sandbox/scanners.py`); runs credential-gated (see Evidence
note) so today it emits `skipped_missing_credential`, becoming active only when a
key is provided.

### Capture (RESEARCH — vendor docs only, NOT live-probed)

```bash
# Primary: scan a directory statically (no execution), emit OSSBOM JSON
ossprey scan <path> -o <ossbom.json>

# Single package by ecosystem
ossprey check -e <pypi|npm> <pkg>[@version]
```

- Install for the Modal image: GitHub release binaries (linux amd64/arm64,
  sudo-less friendly), `install.sh`, or `make build` (Go 1.25+).
- Static parse of manifests/lockfiles, no execution: Python
  (`requirements.txt`, `Pipfile.lock`, `poetry.lock`, `uv.lock`, `pdm.lock`,
  `setup.py`, `pyproject.toml`) and JS (`package.json`, `package-lock.json`,
  `yarn.lock`, `pnpm-lock.yaml`).
- `--local` emits the SBOM to stdout with **no API call**;
  `--dry-run-safe` / `--dry-run-malicious` (the latter injects a fake finding)
  give credential-free test paths. Endpoint `https://api.ossprey.com` is
  overridable via `--url` (mockable in tests).

### Output shape (RESEARCH — vendor docs only)

Two channels, and the adapter must read **both**:

| Channel | Content | Adapter use |
|---|---|---|
| OSSBOM JSON (`-o <file>` or `--local` to stdout) | SBOM of the scanned tree | raw blob → Storage per §0; component inventory |
| Human-readable stdout + **exit code** | the malware **verdict** | drives the finding decision |

**Exit-code disambiguation (load-bearing):**

| Exit | Meaning | Adapter action |
|---|---|---|
| `0` | clean **or** skipped | no finding row |
| `1` | malware **OR** scan failure | must disambiguate error text from a real malware verdict |

Because `1` is overloaded, the adapter emits a **finding only on a positive
malware signal** (verdict text / OSSBOM malware entry) — otherwise exit `1` is a
scan failure → `unreachable`, never a fabricated malware row. A `--json` verdict
flag is **UNVERIFIED**; until confirmed at pin time, parse the documented
human-readable verdict + exit code, not an assumed JSON schema.

**Severity:** any positive malware signal → **`red`** (malware is not tiered;
there is no amber/green malware verdict). Clean/skipped → no row.

### Auth (RESEARCH)

API key `ospy_...` via `--api-key` or `OSSPREY_API_KEY` env (the upstream CLI
also accepts generic `API_KEY`; **Tripwire's adapter reads `OSSPREY_API_KEY`
only** until the contract is VERIFIED); or Auth0 browser login. Key procurement is **[OPEN]** — no key
exists in this environment (slice 35 `🔴 BLOCKED`), so the adapter's live path
is `skipped_missing_credential` today. The credential-free `--local` /
`--dry-run-*` modes exercise parsing without a key.

### References

| Source | URL | Access | Reputation | Status |
|---|---|---|---|---|
| Product site | https://ossprey.com | 2026-08-15 | vendor | vendor docs (not live-probed) |
| GitHub org / `ossprey-cli` | https://github.com/OSSPREY | 2026-08-15 | vendor | vendor docs (not live-probed) |
| API endpoint | https://api.ossprey.com | 2026-08-15 | vendor | referenced, not called |

**Evidence note:** this entry is **RESEARCH** — sourced from Ossprey vendor
docs only and **NOT live-probed**. It must be reconciled against the pinned
`ossprey-cli` version's `--help` and a real OSSBOM sample (and the
still-`UNVERIFIED` `--json` verdict flag) **before it may be labeled VERIFIED**
or block a merge — the same discipline [ADR-0005](../../adr/0005-upstream-scanner-cli-adapters.md)
records ("Exact JSON field names remain RESEARCH until fixture-round-tripped
against the pinned CLI") and the same posture as the adapter module's own
`RESEARCH` docstring. Credential provisioning is `[OPEN]`
([DECISIONS.md](../../plan/DECISIONS.md) 2026-08-15, slice 35 `🔴 BLOCKED`).

**Open:** pin `ossprey-cli` version + reconcile `scan`/`check` flags and OSSBOM
schema against `--help`; confirm or drop the `--json` verdict flag; golden
OSSBOM + verdict fixtures under `fixtures/scanner-samples/ossprey/`
(`--dry-run-malicious` for the positive case); flip to VERIFIED after a
credentialed live round-trip once access lands.

---

## 9. Presend (`presend-adapter`)

Hosted, free supply-chain **heuristics** from [presend.pages.dev](https://presend.pages.dev):
name-similarity typosquat detection (npm, PyPI) and the event-stream pattern
(a previously unseen publisher releasing after long dormancy; npm only). Not
CVE/SCA and not malware detection. Registered after Cargo Audit and before
Ossprey in `SCANNER_GROUPS`; **opt-in**: blank `PRESEND_API_URL` →
`skipped_missing_credential`, no network call.

**ADR-0005 note.** This is the first adapter that calls an HTTP API in-process
instead of wrapping a CLI. [ADR-0005](../../adr/0005-upstream-scanner-cli-adapters.md)
rejected "vendor SaaS HTTP APIs only" because the shipped engines need the target
tree inside the sandbox. Here the tree is read locally (`_find_manifests`, same
cap as DepShield) and only dependency **names** are sent (never versions, paths
or file contents), so that rationale does not apply. There is no Presend CLI to wrap.

### Capture (VERIFIED — live calls to `https://presend.pages.dev`, 2026-09-27)

```
POST {PRESEND_API_URL}/api/typosquat-check          {"ecosystem": "npm" | "PyPI", "packages": [<= 100 names]}
POST {PRESEND_API_URL}/api/maintainer-change-check  {"ecosystem": "npm", "packages": [<= 20 names]}
Headers: Content-Type: application/json + explicit User-Agent
         (Cloudflare answers 403 / error 1010 to urllib's default User-Agent)
```

Up to 100 names per ecosystem (runtime dependencies first; truncation surfaced
in the row detail), so at most 1 + 5 npm requests and 1 PyPI request per scan.
`PRESEND_TIMEOUT` (20 s) bounds the whole group, 10 s per request. Server rate
limit: 10 batch requests per minute per endpoint and client IP.

### Output shape

- typosquat-check (VERIFIED, same live calls): `results[]` of
  `{package, suspicious, similar_to: [{name, distance}], is_known_popular_package, known_legitimate}`.
  PyPI names may come back PEP 503-normalized.
- maintainer-change-check (VERIFIED for the envelope; `flagged_events[]` fields
  from Presend's OpenAPI description, no live positive exists today):
  `results[]` of `{package, found, suspicious, flagged_events: [{version, publisher, published, previous_publisher, dormancy_days, reason, publisher_check}]}`.
  A per-package failure is `{package, error}`.

Mapping: `suspicious: true` → one `dependency_typosquat` finding; each
`flagged_events[]` entry → one `dependency_maintainer_change` finding. Both are
**amber** only (signals for manual review, never red); `advisory_provider:
presend`, `advisory_url` = the package's registry page, `cve_ids: []`.
Fail closed ([ADR-0009](../../adr/0009-fail-closed-incomplete-evidence.md)):
HTTP error, 429, timeout, malformed or short response, per-package `error` or an
unreadable manifest → `unreachable`; findings from completed batches still persist.

Known limits: typosquat-check compares against a curated list of well-known
packages (not a top-N-by-downloads feed); maintainer-change-check is npm-only and
does not detect a hijacked existing account or a malicious release by an
existing maintainer.

### References

| Source | URL | Access | Reputation | Status |
|---|---|---|---|---|
| API docs | https://presend.pages.dev/api | 2026-09-27 | vendor (the adapter's author develops Presend) | live-probed |
| Issue | https://github.com/neomatrix369/tripwire/issues/143 | 2026-09-27 | project | maintainer go-ahead |

**Evidence note:** response shapes were round-tripped against production on
2026-09-27; the unit-test fixtures in `sandbox/tests/test_scanners_presend.py`
mirror them. Egress from the Modal sandbox and the rate limit under concurrent
scans have **not** been exercised live.

---

## 10. Adapter protocol (PROPOSED)

```
run_engine(target, pinned_version) ->
  raw_blob                    # Storage: {scan_run_id}/{scanner_source}/raw.json
  findings: Finding[]         # Postgres
  scan_run_scanner: { scanner_source, status, checks_run }
```

Golden samples: `fixtures/scanner-samples/{engine}/{fixture-name}.json` once smokes exist → mark maps **VERIFIED**.

---

## 11. Work remaining

- [x] Seed `.nwave/trusted-source-domains.yaml`
- [x] Inventory primary docs + pull JSON schemas for Snyk, Cisco Skill Scanner, Cisco MCP Scanner
- [ ] Tessl `--json` field inventory from docs.tessl.io
- [ ] Full Snyk issue-code → Tripwire category table
- [ ] Cisco category / AITech → Tripwire taxonomy table
- [ ] Pin versions + reconcile mcp-scanner CLI vs spec §8
- [ ] Capture golden outputs on Tripwire fixtures
- [ ] Storage key layout ADR one-liner
- [ ] Ossprey: provision access (slice 35 OPEN), pin `ossprey-cli`, reconcile `scan`/`check` + OSSBOM against `--help`, confirm/drop `--json` verdict flag → then VERIFIED
- [ ] Presend: live run from the Modal sandbox (egress, rate limit under concurrent scans) → then VERIFIED end to end
- [ ] Mark each adapter VERIFIED after Supabase round-trip

---

## Changelog

| Date | Change |
|---|---|
| 2026-08-01 | Skeleton + Exa source inventory |
| 2026-08-01 | Filled Snyk / Cisco Skill Scanner / Cisco MCP Scanner field inventories from official raw docs (json-output.md, output-formats.md ×2) |
| 2026-08-15 | Added §7 DepShield (`depshield-mcp`) — MCP-stdio invocation + report-text parse anchors, VERIFIED against live v1.0.0 run; renumbered protocol/work-remaining sections |
| 2026-08-15 | Added §8 Ossprey (`ossprey-adapter`) — malware/malicious-code detection (not CVE), `ossprey scan <path> -o <ossbom.json>`, OSSBOM JSON + exit-code (0 clean / 1 malware-OR-failure) disambiguation, `OSSPREY_API_KEY` auth + `--local`/`--dry-run-*` credential-free modes, malware→`red`. Labeled **RESEARCH** (vendor docs only, not live-probed); credential-gated (`skipped_missing_credential`, access OPEN). Renumbered protocol §8→§9 and work-remaining §9→§10 |
| 2026-09-27 | Added §9 Presend (`presend-adapter`) — opt-in (`PRESEND_API_URL`) hosted typosquat (npm, PyPI) + maintainer-change (npm) heuristics; names only, amber only, fail closed; first in-process HTTP adapter (ADR-0005 note). Shapes live-probed against production. Renumbered protocol §9→§10 and work-remaining §10→§11 |
