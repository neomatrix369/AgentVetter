-- AgentVetter schema (Supabase / Postgres). Source of truth: spec Section 4.
-- Idempotent: safe to re-run via `agentvetter setup` / first-scan auto-bootstrap.

create extension if not exists pgcrypto;

create table if not exists items (
  id               uuid primary key default gen_random_uuid(),
  type             text not null check (type in ('skill', 'mcp_server', 'package')),
  name             text not null,
  identifier       text not null, -- stable name/path grouping key (drift/trend), distinct from content_hash identity
  content_hash     text not null,
  heatmap_status   text not null default 'grey' check (heatmap_status in ('red','amber','green','grey','error')),
  risk_score       numeric,
  quality_score    numeric,
  install_locus    text not null default 'unknown' check (install_locus in ('local','cloud','unknown')),
  source_availability text not null default 'unknown' check (source_availability in (
    'source_on_disk','cloneable','introspection_only','unavailable','unknown'
  )),
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  unique (content_hash)
);
create index if not exists items_identifier_idx on items (identifier);

create table if not exists scan_batches (
  id                 uuid primary key default gen_random_uuid(),
  source_path        text not null,
  item_count         integer not null,
  concurrency_limit  integer not null default 5,
  created_at         timestamptz not null default now()
);

create table if not exists scan_runs (
  id            uuid primary key default gen_random_uuid(),
  item_id       uuid not null references items(id),
  batch_id      uuid references scan_batches(id),
  -- 'running' is an addition over the spec's literal 3-value enum: the CLI must create
  -- this row (to hand scan_run_id to the sandbox) before the outcome is known, and the
  -- sandbox flips it to complete/partial-failed/failed on completion or timeout.
  status        text not null default 'running' check (status in ('running','complete','partial-failed','failed')),
  risk_score    numeric,
  started_at    timestamptz not null default now(),
  completed_at  timestamptz
);
create index if not exists scan_runs_item_idx on scan_runs (item_id, started_at desc);

-- Dashboard read model: one latest scan_run row per item (deterministic tie-break on id).
create or replace view dashboard_latest_runs with (security_invoker = true) as
select distinct on (item_id) *
from scan_runs
order by item_id, started_at desc, id desc;

create table if not exists scan_run_scanners (
  id             uuid primary key default gen_random_uuid(),
  scan_run_id    uuid not null references scan_runs(id),
  scanner_source text not null,
  status         text not null check (status in (
    -- Tessl 5-row states (Wave 12-L design § a)
    'not_started','needs_setup','blocked','queued','running',
    'retrying','interrupted','completed','stale','failed','timed_out',
    -- Legacy states still written by Cisco/Snyk/DepShield/Ossprey adapters
    'skipped_missing_credential','unreachable','not_applicable'
  )),
  checks_run     integer,
  detail         text,  -- human-readable summary (e.g. "3 checks — 1 finding (red): injection")
  console_output text,  -- raw stdout/stderr from scanner subprocess (truncated)
  started_at     timestamptz,
  completed_at   timestamptz
);
-- Slice 64: widen items.type for package / DepShield / Ossprey targets (idempotent).
-- Must not swallow errors: a silent failure leaves the pre-package CHECK in place
-- and `INSERT type='package'` dies on items_type_check.
do $$ begin
  alter table items drop constraint if exists items_type_check;
  alter table items add constraint items_type_check check (type in (
    'skill', 'mcp_server', 'package'
  ));
end $$;

-- Additive migrations for DBs created before these columns existed:
alter table scan_run_scanners add column if not exists detail text;
alter table scan_run_scanners add column if not exists console_output text;
alter table scan_run_scanners add column if not exists started_at timestamptz;
alter table scan_run_scanners add column if not exists completed_at timestamptz;
-- Widen status enum for existing DBs (idempotent: no-op if already correct).
-- Wave 12-L: extends to 14-state list (11 new Tessl states + 3 legacy adapter values).
do $$ begin
  alter table scan_run_scanners drop constraint if exists scan_run_scanners_status_check;
  alter table scan_run_scanners add constraint scan_run_scanners_status_check check (status in (
    'not_started','needs_setup','blocked','queued','running',
    'retrying','interrupted','completed','stale','failed','timed_out',
    'skipped_missing_credential','unreachable','not_applicable'
  ));
exception when others then null;
end $$;
-- Tessl 5-row per-feature run-ID columns (all nullable; idempotent; Wave 12-L § a).
alter table scan_run_scanners add column if not exists tessl_run_id text;
alter table scan_run_scanners add column if not exists tessl_run_id_at timestamptz;
alter table scan_run_scanners add column if not exists resume_checkpoint jsonb;
alter table scan_run_scanners add column if not exists upstream_run_ids jsonb;

create table if not exists findings (
  id                 uuid primary key default gen_random_uuid(),
  scan_run_id        uuid not null references scan_runs(id),
  item_id            uuid not null references items(id),
  severity           text not null check (severity in ('red','amber','green')),
  category           text not null,
  file_path          text,
  location           text,
  entity_kind        text check (entity_kind in ('tool','prompt','resource','server')),
  entity_name        text,
  field_name         text,
  related_tool_names text[],
  package_name       text,
  package_version    text,
  cve_ids            text[],
  cwe_ids            text[],
  advisory_url       text,
  advisory_provider  text,
  snippet            text,
  message            text,
  scanner_source     text not null,
  created_at         timestamptz not null default now()
);
create index if not exists findings_item_idx on findings (item_id);
create index if not exists findings_scan_run_idx on findings (scan_run_id);

create table if not exists coverage (
  id             uuid primary key default gen_random_uuid(),
  scan_run_id    uuid not null references scan_runs(id),
  scanner_source text not null,
  file_path      text,
  entity_name    text,
  scanned        boolean not null
);

-- Slice 67: SIE judge panel + final verdict (separate from ADR-0016 tiered_router findings).
create table if not exists judge_panel_runs (
  id                  uuid primary key default gen_random_uuid(),
  scan_run_id         uuid not null references scan_runs(id),
  item_id             uuid not null references items(id),
  finding_id          uuid references findings(id),
  answered_count      integer not null default 0,
  total_judges        integer not null default 0,
  disagreement        boolean not null default false,
  final_verdict       text check (final_verdict in ('true_positive', 'false_positive', 'needs_review')),
  final_confidence    numeric,
  final_reason        text,
  final_model         text,
  final_raw_response  text,
  prompt_version      text,
  sie_run_id          text,
  inventory_note      text,  -- e.g. <3 suitable models: parallel re-runs of available model(s)
  created_at          timestamptz not null default now()
);
create index if not exists judge_panel_runs_scan_run_idx on judge_panel_runs (scan_run_id);
create index if not exists judge_panel_runs_item_idx on judge_panel_runs (item_id);
create index if not exists judge_panel_runs_finding_idx on judge_panel_runs (finding_id);

create table if not exists judge_panel_judgements (
  id             uuid primary key default gen_random_uuid(),
  panel_run_id   uuid not null references judge_panel_runs(id),
  slot           integer not null,
  model          text not null,
  verdict        text check (verdict in ('true_positive', 'false_positive', 'needs_review')),
  confidence     numeric,
  reason         text,
  raw_response   text,
  prompt_version text,
  run_id         text,
  status         text not null check (status in ('answered', 'timeout', 'error')),
  error_message  text,
  created_at     timestamptz not null default now(),
  unique (panel_run_id, slot)
);
create index if not exists judge_panel_judgements_panel_run_idx on judge_panel_judgements (panel_run_id);

create table if not exists config (
  id                  int primary key default 1,
  monitoring_enabled  boolean not null default true,
  threshold           text not null default 'red',
  llm_provider        text,
  check (id = 1)
);
insert into config (id) values (1) on conflict (id) do nothing;

-- ─── Row Level Security ──────────────────────────────────────────────────────
-- Anon (browser dashboard) may SELECT; writes require service_role (bypasses RLS).
alter table items                   enable row level security;
alter table scan_runs               enable row level security;
alter table scan_run_scanners       enable row level security;
alter table findings                enable row level security;
alter table judge_panel_runs        enable row level security;
alter table judge_panel_judgements  enable row level security;

do $$ begin
  if not exists (select 1 from pg_policies where policyname = 'anon_read_items') then
    create policy anon_read_items             on items              for select to anon using (true);
  end if;
  if not exists (select 1 from pg_policies where policyname = 'anon_read_scan_runs') then
    create policy anon_read_scan_runs         on scan_runs          for select to anon using (true);
  end if;
  if not exists (select 1 from pg_policies where policyname = 'anon_read_scan_run_scanners') then
    create policy anon_read_scan_run_scanners on scan_run_scanners  for select to anon using (true);
  end if;
  if not exists (select 1 from pg_policies where policyname = 'anon_read_findings') then
    create policy anon_read_findings          on findings           for select to anon using (true);
  end if;
  if not exists (select 1 from pg_policies where policyname = 'anon_read_judge_panel_runs') then
    create policy anon_read_judge_panel_runs       on judge_panel_runs       for select to anon using (true);
  end if;
  if not exists (select 1 from pg_policies where policyname = 'anon_read_judge_panel_judgements') then
    create policy anon_read_judge_panel_judgements on judge_panel_judgements for select to anon using (true);
  end if;
end $$;

-- PostgREST needs table GRANTs in addition to RLS policies (tables created via
-- raw SQL as postgres do not always inherit default API grants).
grant usage on schema public to anon, authenticated;
grant select on table items, scan_runs, scan_run_scanners, findings,
  judge_panel_runs, judge_panel_judgements to anon, authenticated;
grant select on dashboard_latest_runs to anon, authenticated;

-- Rollup function: recompute an item's heatmap_status/risk_score from its latest scan_run.
-- heatmap_status = worst-of actionable findings (any red → red; else any amber → amber;
-- else green when ≥1 engine completed). risk_score stays weighted density for sort/trend.
-- complete with zero completed engines (all not_applicable / skipped) → grey (unscanned),
-- not a false green. partial-failed with zero completed → error. failed / running → error.
create or replace function agentvetter_rollup_item(p_item_id uuid) returns void as $$
declare
  v_latest_run_id uuid;
  v_latest_status text;
  v_total_checks numeric;
  v_red_count integer;
  v_amber_count integer;
  v_risk numeric;
  v_bucket text;
begin
  select id, status into v_latest_run_id, v_latest_status
  from scan_runs where item_id = p_item_id order by started_at desc limit 1;

  if v_latest_run_id is null then
    update items set heatmap_status = 'grey', risk_score = null, updated_at = now() where id = p_item_id;
    return;
  end if;

  -- Hard failure / still-running / unknown: paint error (no risk from incomplete work).
  if v_latest_status not in ('complete', 'partial-failed') then
    update items set heatmap_status = 'error', updated_at = now() where id = p_item_id;
    return;
  end if;

  select coalesce(sum(checks_run), 0) into v_total_checks
  from scan_run_scanners where scan_run_id = v_latest_run_id and status = 'completed';

  -- partial-failed with zero completed engines has nothing to score → error.
  if v_latest_status = 'partial-failed' and v_total_checks = 0 then
    update items set heatmap_status = 'error', risk_score = null, updated_at = now() where id = p_item_id;
    return;
  end if;

  -- complete with zero completed engines (all N/A / skipped) → unscanned, not green.
  if v_latest_status = 'complete' and v_total_checks = 0 then
    update items set heatmap_status = 'grey', risk_score = null, updated_at = now() where id = p_item_id;
    update scan_runs set risk_score = null where id = v_latest_run_id;
    return;
  end if;

  select count(*) filter (where severity = 'red'), count(*) filter (where severity = 'amber')
  into v_red_count, v_amber_count
  from findings where scan_run_id = v_latest_run_id and scanner_source != 'tiered_router';

  v_risk := (3 * v_red_count + 1 * v_amber_count) / v_total_checks;

  -- Card colour is an alarm (worst-of), not density. risk_score still dilutes.
  if v_red_count > 0 then
    v_bucket := 'red';
  elsif v_amber_count > 0 then
    v_bucket := 'amber';
  else
    v_bucket := 'green';
  end if;

  update items set heatmap_status = v_bucket, risk_score = v_risk, updated_at = now() where id = p_item_id;
  update scan_runs set risk_score = v_risk where id = v_latest_run_id;
end;
$$ language plpgsql;


-- ─── Legacy cleanup ─────────────────────────────────────────────────────────
-- Drop old tripwire-branded function that was renamed to agentvetter_rollup_item.
drop function if exists tripwire_rollup_item(uuid);

-- ─── Supabase Realtime ──────────────────────────────────────────────────────
-- Enable Realtime publication so the browser dashboard receives INSERT/UPDATE
-- events within ~1s of Modal writing scanner results (replaces 8s polling).
-- The supabase_realtime publication already exists on Supabase-hosted projects.
-- Run once in the SQL Editor or via `psql`.
do $$ begin
  alter publication supabase_realtime add table scan_runs;
exception when others then null;
end $$;

do $$ begin
  alter publication supabase_realtime add table scan_run_scanners;
exception when others then null;
end $$;

do $$ begin
  alter publication supabase_realtime add table findings;
exception when others then null;
end $$;
