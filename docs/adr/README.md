# Architecture Decision Records

Formal ADRs for durable technology and boundary choices.

Planning-level decisions (slice waivers, priority, review skips, model split)
stay in [plan/DECISIONS.md](../plan/DECISIONS.md). Use an ADR when the choice
should outlive a single slice and constrain runtime topology, security, or
quality gates.

Status values: **Proposed**, **Accepted**, **Deprecated**, **Superseded**.

**0001** is **Proposed**, not Accepted: it records an intended Monk packaging /
deployment path that is **not implemented**. The supported Live path remains the
operator workstation flow. Implementation planning is Wave **15-O** (**O0** +
slices 58–61) in [plan/TRAIL.md](../plan/TRAIL.md). Records **0002** and above
are Accepted.

| ADR | Title | Status |
|-----|-------|--------|
| [0001](./0001-monk-deployment-and-packaging.md) | Monk Kit for Live deployment and packaging | Proposed |
| [0002](./0002-node-cli-python-sandbox-split.md) | Node CLI and Python sandbox as separate runtimes | Accepted |
| [0003](./0003-modal-isolated-scanner-execution.md) | Modal for isolated scanner execution | Accepted |
| [0004](./0004-supabase-system-of-record.md) | Supabase/Postgres as system of record | Accepted |
| [0005](./0005-upstream-scanner-cli-adapters.md) | Wrap upstream scanner CLIs; normalize findings | Accepted |
| [0006](./0006-live-mock-strangler-acl.md) | Live vs Mock strangler ACL | Accepted |
| [0007](./0007-html-prototype-ship-ui.md) | HTML prototype dashboard as Horizon A ship UI | Accepted |
| [0008](./0008-anon-read-service-role-write.md) | Anon read, service-role write | Accepted |
| [0009](./0009-fail-closed-incomplete-evidence.md) | Fail closed on incomplete evidence | Accepted |
| [0010](./0010-content-hash-idempotency.md) | Content-hash idempotency with `--force` | Accepted |
| [0011](./0011-idempotent-sql-schema-bootstrap.md) | Idempotent SQL schema bootstrap | Accepted |
| [0012](./0012-sandbox-target-acquisition.md) | Sandbox target acquisition | Accepted |
| [0013](./0013-ship-path-quality-gates.md) | Ship-path quality gates; dashboard and Guard out of bar | Accepted |
| [0014](./0014-curated-discovery-loci.md) | Curated discovery loci, not a filesystem crawl | Accepted |
| [0015](./0015-horizon-a-excludes-guard-and-drift.md) | Horizon A excludes Guard and Drift | Accepted |
| [0016](./0016-tiered-router-sie-model-studio.md) | Tiered post-scan router via SIE and Model Studio | Accepted |
| [0017](./0017-claude-code-agent-guard-integration.md) | Claude Code Agent Guard integration (amends ADR-0015) | Accepted |
| [0018](./0018-agentvetter-rebrand.md) | AgentVetter rebrand (unified product + repo identity) | Accepted (amended 2026-10-03) |

0002–0017 are retrospective Accepted records of decisions already visible in
docs, git history, and production entry points.
