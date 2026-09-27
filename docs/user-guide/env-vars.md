# Environment variables

> **Configure (keys) SSOT** for every key in [`.env.example`](../../.env.example).
> Create accounts first (**Setup**): [prerequisites vendor map](./prerequisites.md#vendor-setup-map),
> [Supabase](./supabase-setup.md), [Modal](./modal-setup.md), then paste values here.

Start here: [QUICKSTART](../../QUICKSTART.md) · Hub: [docs/README](../README.md)

> **Minimum Viable Live:** Supabase + Modal keys only. Add Snyk / Tessl / Cisco
> when you want full scanner coverage; DepShield needs no keys; Ossprey needs
> `OSSPREY_API_KEY` when access is available. Missing Snyk/Cisco/Ossprey keys report
> `skipped_missing_credential`. Missing `TESSL_TOKEN` still runs Lint (auth-free)
> and marks Review (Quality) / Scenario Generation / Review (Security) `needs_setup`. `TESSL_WORKSPACE`
> is optional — when unset (or set to a name not in `tessl workspace list`),
> Tripwire resolves workspace via `tessl whoami` + `tessl workspace list`
> (usually the Tessl username). Eval stays `blocked` until
> Scenario Gen completes (then `needs_setup` if token or workspace/project link
> cannot be established) — not a complete “all clear.”
>
> For full Live coverage, provision credentialed scanner vendors before `cp .env.example .env`.
>
> **Cost and billing:** creating accounts, provisioning resources, deploying
> Modal apps, and running Live scans can incur charges or consume provider
> quotas. Review billing and usage controls before proceeding; use the local
> Mock path when you do not intend to incur costs.
>
> Account-creation how-tos live on vendor setup pages; this page owns key names
> and procurement mapping. The [setup command catalog](./setup-commands.md)
> owns command order; the
> [Modal scanner-secret reference](../../fixtures/OPTIONAL_SCANNER_KEYS.md)
> owns only the Modal secret allowlist and safe sync behavior.

Companion allowlist: [OPTIONAL_SCANNER_KEYS.md](../../fixtures/OPTIONAL_SCANNER_KEYS.md).

## Which keys do I need?

| Goal | Keys |
|---|---|
| Demo / Mock only | None — skip `.env` |
| Live platform (store + sandbox) | All `SUPABASE_*` + `MODAL_TOKEN_*` |
| Full scanner coverage | Platform + `SNYK_TOKEN` + `TESSL_*` + Cisco Skill/MCP / AI Defense keys below |
| Optional post-scan routing | `SIE_ENDPOINT` + `SIE_API_KEY` (required); Model Studio keys for escalation |
| Sample SIE / Model Studio CLIs only | Same router keys; may also live in `prototypes/.env` |

Procurement steps: [vendor procurement quick-steps](#vendor-procurement-quick-steps).
Router how-to: [tiered-router-setup.md](./tiered-router-setup.md).

## Scope boundary

This is the sole reference for **Configure** — credential procurement, every
`.env` key, and key-to-capability mapping. Account creation (**Setup**) is owned
by vendor setup pages and the [prerequisites map](./prerequisites.md#vendor-setup-map).
Do not duplicate key explanations in the Modal secret reference.
[OPTIONAL_SCANNER_KEYS.md](../../fixtures/OPTIONAL_SCANNER_KEYS.md)
only projects a selected subset of these already-defined keys into
`tripwire-scan-secrets`; repeated names there are operational allowlist entries,
not a second environment-variable schema.

## Platform plumbing

| Key | Required for | Where to get it |
|-----|--------------|-----------------|
| `SUPABASE_URL` | Platform / Live / Modal HTTP | [supabase-setup](./supabase-setup.md) → Project Settings → API → Project URL |
| `SUPABASE_ANON_KEY` | Live browser | [supabase-setup](./supabase-setup.md) → API → `anon` `public`; if needed use `scripts/serve-dashboard.mjs` proxy instead |
| `SUPABASE_SERVICE_ROLE_KEY` | Platform writes + Modal | [supabase-setup](./supabase-setup.md) → API → `service_role` (server only) |
| `SUPABASE_DB_URL` | `tripwire setup` DDL | [supabase-setup](./supabase-setup.md) → Database → connection string (`postgresql://…`) |
| `MODAL_TOKEN_ID` | Non-interactive Modal setup | [modal-setup](./modal-setup.md) → Settings / Tokens or `modal token new` |
| `MODAL_TOKEN_SECRET` | Non-interactive Modal setup | [modal-setup](./modal-setup.md) → Settings / Tokens or `modal token new` |

## Tier B — Semantic (recommended MVP)

| Key | Required for | Where to get it |
|-----|--------------|-----------------|
| `SNYK_TOKEN` | Snyk skill/MCP depth | [Vendor procurement quick-steps](#vendor-procurement-quick-steps) in this file |
| `SKILL_SCANNER_LLM_API_KEY` | Cisco Skill Scanner `--use-llm` | [Vendor procurement quick-steps](#vendor-procurement-quick-steps) in this file |
| `SKILL_SCANNER_LLM_MODEL` | Skill LLM routing | [Vendor procurement quick-steps](#vendor-procurement-quick-steps) in this file |
| `SKILL_SCANNER_LLM_PROVIDER` | Custom / OpenAI-compatible | [Vendor procurement quick-steps](#vendor-procurement-quick-steps) in this file |
| `SKILL_SCANNER_LLM_BASE_URL` | Custom LLM endpoint | [Vendor procurement quick-steps](#vendor-procurement-quick-steps) in this file |
| `SKILL_SCANNER_LLM_API_VERSION` | Azure-style APIs | [Vendor procurement quick-steps](#vendor-procurement-quick-steps) in this file |
| `MCP_SCANNER_LLM_API_KEY` | Cisco MCP Scanner `behavioral` | [Vendor procurement quick-steps](#vendor-procurement-quick-steps) in this file |
| `MCP_SCANNER_LLM_MODEL` | MCP LLM routing | [Vendor procurement quick-steps](#vendor-procurement-quick-steps) in this file |
| `MCP_SCANNER_LLM_BASE_URL` | Custom MCP LLM endpoint | [Vendor procurement quick-steps](#vendor-procurement-quick-steps) in this file |
| `MCP_SCANNER_LLM_API_VERSION` | Azure-style APIs | [Vendor procurement quick-steps](#vendor-procurement-quick-steps) in this file |
| `TESSL_TOKEN` | Tessl Review (Quality + Security) / Scenario Gen / Eval on Modal/CI (Lint is auth-free) | [Vendor procurement quick-steps](#vendor-procurement-quick-steps) in this file |
| `TESSL_WORKSPACE` | Optional override for Tessl `--workspace` (Review / Scenario Gen / project create). Must match a workspace from `tessl workspace list` (name or id); invalid values are ignored and auto-resolved (usually the username) | [Vendor procurement quick-steps](#vendor-procurement-quick-steps) in this file |

## Tier C — Full depth (paid Cisco AI Defense)

| Key | Required for | Where to get it |
|-----|--------------|-----------------|
| `AI_DEFENSE_API_KEY` | Skill Scanner `--use-aidefense` | [Vendor procurement quick-steps](#vendor-procurement-quick-steps) in this file |
| `AI_DEFENSE_API_URL` | Custom AI Defense API host | [Vendor procurement quick-steps](#vendor-procurement-quick-steps) in this file |
| `MCP_SCANNER_API_KEY` | MCP Scanner cloud inspect | [Vendor procurement quick-steps](#vendor-procurement-quick-steps) in this file |
| `MCP_SCANNER_ENDPOINT` | MCP inspect API base | [Vendor procurement quick-steps](#vendor-procurement-quick-steps) in this file |

## DepShield — no keys required

The DepShield dependency-audit adapter (`depshield-mcp`, baked into the Modal
image) needs **no vendor account and no `.env` keys**: it audits npm and PyPI
manifests via OSV.dev over plain network egress from the sandbox. There is
nothing to procure here and nothing to add to `tripwire-scan-secrets`; the
`skipped_missing_credential` degraded path does not apply to this engine.

## Ossprey — malware scan (access OPEN / pending)

The Ossprey adapter (`ossprey-cli`, [ossprey.com](https://ossprey.com)) detects
**malicious code / malware** in open-source packages — distinct from Snyk and
DepShield, which audit dependency **CVEs**. Access provisioning is currently
**[OPEN]**: no key is available in this environment, so the adapter safely
reports `skipped_missing_credential` and becomes active only once a key is set.

| Key | Required for | Where to get it |
|-----|--------------|-----------------|
| `OSSPREY_API_KEY` | Ossprey malware scan (once access lands) | [Vendor procurement quick-steps](#vendor-procurement-quick-steps) in this file — **pending access** |

The value is an `ospy_…` key from `ossprey init` or the vendor dashboard. Tripwire's
adapter reads **`OSSPREY_API_KEY` only** (generic `API_KEY` is ignored until the
vendor contract is VERIFIED). The upstream CLI may accept other auth modes (Auth0,
`API_KEY`); Tripwire does not wire those into Modal secrets. The key is allowlisted in
[OPTIONAL_SCANNER_KEYS.md](../../fixtures/OPTIONAL_SCANNER_KEYS.md) so
`setup-modal.sh` syncs it into `tripwire-scan-secrets` automatically when it
becomes available; leave it blank until then. Credential-free `--local` /
`--dry-run-safe` / `--dry-run-malicious` modes exist for local testing without a
key.

## Presend — typosquat / maintainer-change signals (opt-in)

The Presend adapter sends the **dependency names** found in `package.json` /
`requirements.txt` (never versions, paths or file contents) to the hosted Presend
API: typosquat-check (npm, PyPI) and maintainer-change-check (npm). It is the only
scanner that sends data to a third-party HTTP API from inside the Tripwire
process, so it is **opt-in**: leave `PRESEND_API_URL` blank and the adapter
reports `skipped_missing_credential` without any network call.

| Key | Required for | Where to get it |
|-----|--------------|-----------------|
| `PRESEND_API_URL` | Presend adapter (opt-in) | `https://presend.pages.dev` — no account, no key; per-IP rate limits (10 batch requests/min per endpoint) |

Findings are amber only (heuristic signals for manual review). The URL is
allowlisted in [OPTIONAL_SCANNER_KEYS.md](../../fixtures/OPTIONAL_SCANNER_KEYS.md)
so `setup-modal.sh` syncs it into `tripwire-scan-secrets` when set.

## Optional — tiered router (SIE + Model Studio)

Not required for scanner Live coverage. Required for `tripwire route` and for
post-scan auto-route after `tripwire scan` ([ADR-0016](../adr/0016-tiered-router-sie-model-studio.md)).
If these keys are absent, scan still completes and auto-route logs a warning
and skips. Prototype CLIs under `prototypes/sie-studio/` and
`prototypes/model-studio/` use the same keys (also listed in
`prototypes/.env.example`).

| Key | Required for | Where to get it |
|-----|--------------|-----------------|
| `SIE_ENDPOINT` | Tiered router + SIE sample CLI | [tiered-router-setup](./tiered-router-setup.md) — us-east-2 `https://api.superlinked.com`; EU `https://eu.api.superlinked.com` |
| `SIE_API_KEY` | Tiered router + SIE sample CLI | [tiered-router-setup](./tiered-router-setup.md) — Superlinked console → Keys (`sk-sie-…`) |
| `SIE_MODEL` | Optional SIE model override (default `gen-4b`) | [tiered-router-setup](./tiered-router-setup.md) / `prototypes/sie-studio/models.json` |
| `TRIPWIRE_JUDGE_PANEL` | Opt-in post-scan judge panel (`1` = soft-fail after auto-route; default off) | Slice 67; ADR-0016 route unchanged when unset |
| `DASHSCOPE_API_KEY` | Model Studio escalation + sample CLI | [tiered-router-setup](./tiered-router-setup.md) |
| `DASHSCOPE_HOST` | Optional host used to derive Model Studio URLs when blank | [tiered-router-setup](./tiered-router-setup.md) |
| `ALIBABA_OPENAI_BASE_URL` | Router Model Studio chat + `model_studio.py chat` | [tiered-router-setup](./tiered-router-setup.md) |
| `ALIBABA_DASH_SCOPE_API_URL` | Sample CLI image/video only | [tiered-router-setup](./tiered-router-setup.md); not required by the CLI router |
| `MODEL_STUDIO_MODEL` | Optional Model Studio model override (default `qwen3.8-max`) | [tiered-router-setup](./tiered-router-setup.md) |

## Wire into Modal

```bash
./scripts/setup-modal.sh
# or secrets only: ./scripts/setup-modal.sh --secrets-only
```

See [modal-setup.md](./modal-setup.md). The [Modal scanner-secret reference](../../fixtures/OPTIONAL_SCANNER_KEYS.md)
explains the allowlist and why the helper must be used instead of a manual
secret-creation command.

## Vendor procurement quick-steps

Account creation (Setup) is owned by the vendor setup pages. This table maps each
vendor to the keys you need in `.env` and where to get them.

| Vendor | Keys (set in `.env`) | Setup guide |
|---|---|---|
| **Supabase** (platform — MVP) | `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_DB_URL` | [supabase-setup](./supabase-setup.md) |
| **Modal** (platform — MVP) | `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` (blank if interactive only) | [modal-setup](./modal-setup.md) |
| **Snyk** (scanner) | `SNYK_TOKEN` | [app.snyk.io](https://app.snyk.io) → Settings → API Tokens |
| **Tessl** (scanner) | `TESSL_TOKEN` (required); `TESSL_WORKSPACE` (optional override) | [tessl.io](https://tessl.io) → API key. Lint (`tessl skill lint`) is auth-free. Token gates Review (Quality + Security) / Scenario / Eval. Workspace for `--workspace` comes from `TESSL_WORKSPACE` or `tessl whoami` + `workspace list` (personal workspace ≈ username). Scenario Gen also needs `.tessl-plugin/plugin.json`. Eval auto-chains after Scenario Gen when `evals/` is populated; needs a linked Tessl project (`tessl.json` — adapter runs `project create` / `repair`). Security Review runs after Eval and links `upstream_run_ids.review_quality` — see [tessl-5-row-expansion](../design/tessl-5-row-expansion.md). |
| **Cisco Skill / MCP LLM** (scanner Tier B) | `SKILL_SCANNER_LLM_API_KEY`, `SKILL_SCANNER_LLM_MODEL`, `SKILL_SCANNER_LLM_PROVIDER`, `SKILL_SCANNER_LLM_BASE_URL`; `MCP_SCANNER_LLM_API_KEY`, `MCP_SCANNER_LLM_MODEL`, `MCP_SCANNER_LLM_BASE_URL` | Any OpenAI-compatible or Azure LLM — not the same as AI Defense cloud keys below |
| **Cisco AI Defense** (scanner Tier C) | `AI_DEFENSE_API_KEY`, `MCP_SCANNER_API_KEY`; optional `AI_DEFENSE_API_URL`, `MCP_SCANNER_ENDPOINT` | [developer.cisco.com](https://developer.cisco.com) → AI Defense |
| **Ossprey** (malware — access OPEN/pending) | `OSSPREY_API_KEY` (`ospy_…`) | Access not yet available — leave blank; adapter reports `skipped_missing_credential` |
| **Presend** (supply-chain signals — opt-in) | `PRESEND_API_URL` | No key. Blank keeps it off (`skipped_missing_credential`); `https://presend.pages.dev` turns it on |
| **SIE** (optional router) | `SIE_ENDPOINT`, `SIE_API_KEY`; optional `SIE_MODEL` | [tiered-router-setup](./tiered-router-setup.md) |
| **Model Studio** (optional router) | `DASHSCOPE_API_KEY`, `ALIBABA_OPENAI_BASE_URL`; optional `DASHSCOPE_HOST`, `MODEL_STUDIO_MODEL`, `ALIBABA_DASH_SCOPE_API_URL` | [tiered-router-setup](./tiered-router-setup.md) |
