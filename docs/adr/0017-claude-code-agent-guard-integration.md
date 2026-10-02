# ADR-0017: Claude Code Agent Guard integration (amends ADR-0015)

- **Status:** Accepted
- **Date:** 2026-08-15
- **Deciders:** Tripwire maintainers
- **Tags:** guard, claude-code, hooks, enforcement, fail-closed, hackathon

## Context

Frontline Hackathon London 2026 targets a Claude Code integration layer:
Tripwire verdicts enforced at the moment an agent invokes a skill or MCP tool.
[ADR-0015](./0015-horizon-a-excludes-guard-and-drift.md) scoped Guard out of
Horizon A and states that re-opening Guard requires *a new ADR plus STATUS
evidence, not a stub file*. This is that ADR; the matching STATUS entries are
**PROPOSED** and flip to IMPLEMENTED/VERIFIED only with the Phase-1
regression-gate evidence.

Two verified facts about Claude Code hooks drive the design: a plain non-zero
exit from a PreToolUse hook is a *non-blocking* error (the tool call proceeds),
and a hook killed by its own configured timeout also lets the call proceed.
Fail-closed therefore has to be built from explicit decisions and an internal
time budget, never from exit codes or the external timeout.

## Decision

Guard ships as the **Claude Code PreToolUse enforcement layer**, per the
hackathon working plan ("Tripwire × Claude Code Integration — Implementation
Plan", 2026-08-15 session working document):

- **Handler at `~/.tripwire/hooks/`** (`pre-tool-use.sh` + `_guard_entry.py`),
  registered under matcher `^(Skill|Bash|mcp__.*)$` in `~/.claude/settings.json`
  (JSON-merge preserving existing keys, timestamped backup first). Repo source
  is a tracked `agent-hooks/` directory. Bash is gated only when the command
  *executes* under a skills locus (cwd inside the skill, a file under it, or
  `cd <skill> && bash …`); ordinary Bash and skill dirs passed only as data
  args are not attributed.
- **Identifier-first lookup + CLI-compatible hash comparison.** Items are
  looked up by `items.identifier` (canonical absolute path, `updated_at desc
  limit 1`), and the CLI's sorted-directory-walk SHA-256 (`cli/src/hash.js`,
  ported to `guard/status.py`) is recomputed and compared against the stored
  `content_hash`. Mismatch denies with "content changed since last scan" — a
  green verdict authorizes specific bytes, not a path. MCP servers are the
  exception: their identity is the config key alone (never a path derived
  from attacker-controlled `command`/`args`), their stored hashes stay
  `pending:<key>`, and consequently MCP verdicts carry no content binding
  and same-named keys in different projects share one identity row — an
  accepted consequence of the plan's §5.4 manifest-only rule.
- **Fail-closed contract, including the timeout-budget rule.** The handler
  always exits 0 with an explicit allow/deny decision JSON (dual
  modern+legacy shape); an ERR/EXIT trap emits deny if no decision was
  printed; the Python entry runs under an internal 8-second watchdog
  (portable; no GNU timeout dependency) strictly below the hook's 10s so a
  hang becomes a trapped deny, never an external kill that fails open; the
  Supabase client carries a ~5s timeout. Staleness (default 14-day validity
  window) and calls that resolve to no known artifact also deny. Aligned
  with [ADR-0009](./0009-fail-closed-incomplete-evidence.md).
- **Local config AND-ed with Supabase.** `~/.tripwire/config.json` holds the
  Claude-Code-layer kill switch (`enable`) plus `scan_validity_days` and
  recorded absolute paths. Effective enforcement = local `enable` **AND** the
  existing Supabase `config.monitoring_enabled` (that guard logic is
  untouched). Missing/unparseable config is a tamper signal and **denies**;
  the only bypass is an explicit, parseable `"enable": false`.
- **Five `/tw-*` skills** — `tw-verify`, `tw-scan`, `tw-enable`,
  `tw-disable`, `tw-self-check` — shipped from `agent-hooks/skills/`,
  installed to `~/.claude/skills/`, all driving shared helper logic in
  `guard/status.py`.
- **`tripwire setup-agent-hooks` installer** (`cli/bin/tripwire.js` +
  `cli/src/setupAgentHooks.js`): preflight hard-fails, config init, handler
  install, guard-environment pre-warm, settings JSON-merge, skill copy, and a
  bootstrap scan sweep (tw skills + demo artifacts + configured MCP servers)
  so going live does not instantly block everything.

### Honest limits (recorded, not hidden)

- **Same-user Bash tampering (enable flip).** An injected agent can still
  `Bash`-write `"enable": false` (or delete/corrupt the config) in a single
  call — that path is unmatched by skill-path attribution. Missing/corrupt
  config denies, but a correctly-written disable bypasses enforcement —
  unfixable at this layer. Detection is advisory only, via the optional
  SessionStart sweep that loudly reports enforcement state at session start.
- **Bash skill-path attribution (closed gap).** Matcher is
  `^(Skill|Bash|mcp__.*)$`. Bash is allowed immediately unless the command
  *executes* under a skills locus (cwd inside the skill, a file under it such
  as `install.sh`, or `cd <skill> && bash …`); then the owning skill's
  verdict gates the call. Skill directories passed only as data args (status/
  scan drivers) are not attributed — otherwise unscanned skills would
  deadlock `/tw-verify` and `/tw-scan`. This closes the slash-command path
  where `/vuln-skill` injects instructions and the agent runs `install.sh`
  via Bash without a Skill tool PreToolUse event.
- **User-typed Skill tool events.** Whether user-typed (vs model-initiated)
  skill invocations produce a hook-visible Skill event is still harness-
  dependent; Bash attribution above covers the dangerous follow-on
  execution. Custom slash commands (`.claude/commands`) remain out of
  Phase-1 scope for non-skill paths.
- **Service-role key in the hook environment.** Accepted for the hackathon:
  the key stays in `.env` (never in `settings.json`; gitleaks runs
  repo-wide), but every intercepted call sources it. An anon-key read path
  for the guard is backlogged — this tension with
  [ADR-0008](./0008-anon-read-service-role-write.md)'s read/write split is
  acknowledged, not resolved.

### Scope

This ADR **amends** ADR-0015; it does not fully supersede it. Only the Guard
PreToolUse exclusion is reopened, with the evidence discipline intact.
**Drift/trend/diff stays Won't (A)**, as do ADR-0015's other exclusions.

## Consequences

- `guard/` gains real production entry points (`guard/entry.py`,
  `guard/status.py`, `check_call_by_identifier` in `guard/guard_hook.py`).
  Test-coverage intent for the new modules (≥90%) is recorded in
  [DECISIONS.md](../plan/DECISIONS.md) (2026-08-15); the full coverage
  ratchet is a follow-up slice — `guard/` stays outside the
  [ADR-0013](./0013-ship-path-quality-gates.md) bars until it lands.
- **Wave-G overlap:** `setup-agent-hooks` lands in `cli/bin/tripwire.js`, the
  same file slice 18's Commander refactor touches. Sequence rule: one active
  slice per shared code area — land the subcommand before slice 18 starts, or
  rebase onto it (called out in TRAIL/PROGRESS).
- STATUS claims stay PROPOSED until the Phase-1 regression gate (live
  block/allow matrix, tamper case, fail-closed refusal+hang pair,
  `~/.claude/settings.json` diff) records evidence.
- The §5.4 relative-identifier cleanup ships as a printed, operator-reviewed
  `psql` command in `scripts/install-demo-artifacts.sh` — a deliberate manual
  step, never executed by the tooling itself.
- Re-mentioning Ossprey in top-level docs stays gated: the trust-strip check
  must be superseded via a DECISIONS.md row when Phase 3 starts — never
  silently (placeholder recorded in DECISIONS.md 2026-08-15).

## Addendum (2026-08-15): DepShield identification

DepShield in the hackathon plan is the `depshield-mcp` npm package (an
MCP-stdio dependency auditor covering npm + PyPI via OSV.dev, zero
credentials, baked into the Modal image) — not Sonatype's discontinued,
GitHub-app-only DepShield. Because the adapter is entirely sandbox-side with
no credentials, plan step 8's "DepShield install path in `setup-agent-hooks`"
collapsed to a no-op ([DECISIONS.md](../plan/DECISIONS.md) 2026-08-15). Its
dependency findings populate the previously-dormant `findings` columns
(package/version/advisory anchors) that earlier scanners left empty.

## Addendum (2026-08-15): Ossprey adapter

Ossprey ([ossprey.com](https://ossprey.com), `ossprey-cli`) joins as the
**second dispatch extension** after DepShield — an open-source malware /
malicious-code detector (distinct from DepShield's dependency-CVE audit),
registered after DepShield in `SCANNER_GROUPS`. It ships **RESEARCH-labeled**
(vendor docs only, not live-probed; reconcile against the pinned CLI `--help` /
OSSBOM schema before VERIFIED, per [ADR-0005](./0005-upstream-scanner-cli-adapters.md))
and **credential-gated** — access provisioning is OPEN, so it emits
`skipped_missing_credential` until an `OSSPREY_API_KEY` exists
([DECISIONS.md](../plan/DECISIONS.md) 2026-08-15). Because there is no
user-facing functionality yet, the trust-strip gate is preserved unchanged: no
Ossprey mention enters README/QUICKSTART/CONTRIBUTING/STATUS/ARCHITECTURE until
provisioning and live verification land, consistent with the Ossprey re-mention
gate above.

## Addendum (2026-09-27): Presend adapter (proposed, issue #143)

Presend joins as the **third dispatch extension**, registered after Cargo Audit
and before Ossprey, which stays the final group. It sends dependency names read
from `package.json` / `requirements.txt` to a hosted API for two heuristic
signals (typosquat: npm + PyPI; new publisher after dormancy: npm) and reports
them as amber findings only. Because it is the first adapter that sends data to
a third party from inside the Tripwire process, it is **opt-in**: blank
`PRESEND_API_URL` → `skipped_missing_credential`, no network call. The tail
budget moves 20 s from `OSSPREY_TIMEOUT` (90 → 70; Ossprey cannot run until
access lands) to `PRESEND_TIMEOUT`, keeping DepShield + Cargo Audit + Presend +
Ossprey = 240 s = `SCAN_TIMEOUT`. Consistent with the re-mention gate above, no
Presend mention enters README/QUICKSTART/CONTRIBUTING/STATUS/ARCHITECTURE.
Details: [scanner-output-adapters.md](../research/adapters/scanner-output-adapters.md) §9.

## Alternatives considered

### A. Keep Guard closed; ship advisory-only skills

Rejected: reporting without enforcement leaves the demo machine unprotected —
`permissions.defaultMode = "bypassPermissions"` there means the PreToolUse
hook is the only pre-execution enforcement layer available.

### B. Fully supersede ADR-0015

Rejected: only the Guard exclusion is being reopened. Drift/trend and the
other exclusions still hold, so an amendment is the honest scope.

### C. Exit-code-based blocking (exit non-zero / exit 2 on deny)

Rejected as the primary mechanism: plain non-zero is non-blocking and a
timed-out hook fails open. Explicit decision JSON plus the internal timeout
budget is the reliable fail-closed path; exit 2 remains an unreachable
backstop only.

## References

- [ADR-0015](./0015-horizon-a-excludes-guard-and-drift.md) (amended by this
  record) · [ADR-0008](./0008-anon-read-service-role-write.md) ·
  [ADR-0009](./0009-fail-closed-incomplete-evidence.md) ·
  [ADR-0013](./0013-ship-path-quality-gates.md)
- Tripwire × Claude Code Integration — Implementation Plan (hackathon working
  document, 2026-08-15; branch `tripwire-frontline-hack`)
- [docs/plan/DECISIONS.md](../plan/DECISIONS.md) 2026-08-15 rows ·
  [docs/STATUS.md](../STATUS.md) PROPOSED section ·
  [docs/plan/TRAIL.md](../plan/TRAIL.md) wave H
