# Modal scanner-secret reference

This is the operational reference for `tripwire-scan-secrets`: the scanner
credentials that `./scripts/setup-modal.sh` may sync from `.env`.

For every provider account, credential value, and environment-variable meaning,
use [env-vars.md](../docs/user-guide/env-vars.md). This file owns only the
Modal secret allowlist and helper-only synchronization behavior.

## Scope boundary

Do not use this file to choose providers, create accounts, obtain credentials,
or determine `.env` values. Those decisions belong exclusively to
[env-vars.md](../docs/user-guide/env-vars.md). The key names below are repeated
only to define the subset that can be copied into the Modal scanner secret; they
are not a second key catalogue.

## Scanner-secret allowlist

`setup-modal.sh` copies only non-empty values for these keys. Configure every
listed capability for the recommended complete Live setup. A missing value safely
skips that scanner engine (`skipped_missing_credential`); it never creates a
placeholder token, but this is a degraded diagnostic path.

| Scanner capability | Keys synced to `tripwire-scan-secrets` |
|---|---|
| Snyk scanning | `SNYK_TOKEN` |
| Tessl Review (Quality + Security), Scenario Gen, Eval | `TESSL_TOKEN`, `TESSL_WORKSPACE` |
| Cisco Skill Scanner LLM | `SKILL_SCANNER_LLM_API_KEY`, `SKILL_SCANNER_LLM_MODEL`, `SKILL_SCANNER_LLM_PROVIDER`, `SKILL_SCANNER_LLM_BASE_URL`, `SKILL_SCANNER_LLM_API_VERSION` |
| Cisco MCP Scanner LLM | `MCP_SCANNER_LLM_API_KEY`, `MCP_SCANNER_LLM_MODEL`, `MCP_SCANNER_LLM_BASE_URL`, `MCP_SCANNER_LLM_API_VERSION` |
| Cisco AI Defense | `AI_DEFENSE_API_KEY`, `AI_DEFENSE_API_URL`, `MCP_SCANNER_API_KEY`, `MCP_SCANNER_ENDPOINT` |
| Ossprey malware scan (access **OPEN** / pending) | `OSSPREY_API_KEY` |
| Presend typosquat / maintainer-change signals (opt-in, no key) | `PRESEND_API_URL` |

Scanner environment variable names stay upstream. Do not add `TRIPWIRE_*` or
`CISCO_AI_DEFENSE_API_KEY` aliases.

**`OSSPREY_API_KEY` is allowlisted but not yet obtainable.** Access provisioning
for the Ossprey adapter is **[OPEN]** — no key exists in this environment
([env-vars.md](../docs/user-guide/env-vars.md) · [DECISIONS.md](../docs/plan/DECISIONS.md)
2026-08-15, slice 35 `🔴 BLOCKED`). The row is present so that once a key
(`ospy_…`) is provided, `setup-modal.sh` syncs it into `tripwire-scan-secrets`
with no further change here. Until then the value stays blank and the adapter
reports `skipped_missing_credential` — unlike DepShield below, Ossprey *does*
take a credential, so it uses that safe-skip path rather than being credential-free.

**`PRESEND_API_URL` is a switch, not a secret.** The Presend adapter needs no
credential, but it sends dependency names to a hosted API, so it runs only when
this URL is set. Blank → `skipped_missing_credential` with no network call, the
same safe-skip path as a missing key.

**DepShield has no row above by design.** The DepShield adapter
(`depshield-mcp`, baked into the Modal image) requires **no credentials**: it
audits npm and PyPI manifests via OSV.dev using plain network egress from the
sandbox. There is nothing to add to `tripwire-scan-secrets` for DepShield, and
no `skipped_missing_credential` path exists for it.

## Sync the secrets

```bash
./scripts/setup-modal.sh --secrets-only
```

Use `./scripts/setup-modal.sh` to sync secrets and deploy the scan app. Both
commands read the repository-root `.env`, use the allowlist above, and never
echo values.

## No manual secret command

Do not replace `./scripts/setup-modal.sh --secrets-only` with a hand-written
`modal secret create ... --force` command. The helper filters empty scanner
values before updating `tripwire-scan-secrets`; a manual command can overwrite
an existing value with a blank one.

If no scanner keys are set, the helper leaves `tripwire-scan-secrets` unchanged
and syncs only the required Supabase secret.
