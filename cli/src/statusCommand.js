import * as defaultFs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { getSupabase } from './supabaseClient.js';
import { isAgentVetterHookCommand, resolveConfigHome } from './configHome.js';

/**
 * `agentvetter status` (slice 37 — CLI monitoring, read-only). Reports:
 *   a. Hooks   — ~/.agentvetter/config.json + Claude
 *                settings registration + the Supabase `config` platform switch
 *                (two-switch rule: effective enforcement = local `enable` AND
 *                `monitoring_enabled`).
 *   b. Items   — heatmap_status distribution.
 *   c. Runs    — last N scan_runs, status counts, stranded `running` rows
 *                (older than 30 min — the known Modal-timeout strand).
 *   d. Scanners — latest status per scanner_source across those runs.
 *
 * STRICTLY read-only (GWT 2): zero Supabase writes (select-family only), zero
 * file writes. Missing Supabase credentials degrade to the local hooks section
 * plus a remediation note and still resolve (exit 0) — half the picture beats
 * a hard failure. Invalid --limit input throws so the bin exits nonzero (GWT 3).
 */

const DEFAULT_LIMIT = 20;
const MAX_LIMIT = 200;
const STRANDED_AFTER_MS = 30 * 60 * 1000;
const STRANDED_REMEDY = 'node scripts/reconcile-stuck-scan-runs.mjs';
const RECENT_LINES_SHOWN = 5;
const HEATMAP_STATUSES = ['red', 'amber', 'green', 'grey', 'error'];

/** Validate --limit: integer 1..MAX_LIMIT (GWT 3 — throw with actionable text). */
function parseLimit(raw) {
  const value = typeof raw === 'number' ? raw : Number(String(raw).trim());
  if (!Number.isInteger(value) || value < 1 || value > MAX_LIMIT) {
    throw new Error(
      `--limit must be an integer between 1 and ${MAX_LIMIT} (got "${raw}"). Example: agentvetter status --limit 50`
    );
  }
  return value;
}

function isPlainObject(value) {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** Does ~/.claude/settings.json register the agentvetter PreToolUse handler? */
function readHookRegistration({ fs, settingsPath, homedir }) {
  try {
    const settings = JSON.parse(fs.readFileSync(settingsPath, 'utf8'));
    const preToolUse = isPlainObject(settings) && isPlainObject(settings.hooks)
      ? settings.hooks.PreToolUse : null;
    if (!Array.isArray(preToolUse)) return false;
    return preToolUse.some(entry =>
      entry && Array.isArray(entry.hooks) && entry.hooks.some(h => h && isAgentVetterHookCommand(h.command, homedir)));
  } catch {
    return false; // absent or unparseable — either way, not verifiably registered
  }
}

/** Local hooks state from config home: installed | disabled/enabled | corrupt. */
function readLocalHooks({ fs, homedir }) {
  const configHome = resolveConfigHome(homedir);
  const configPath = path.join(configHome, 'config.json');
  const settingsPath = path.join(homedir, '.claude', 'settings.json');
  const base = {
    config_path: configPath,
    settings_path: settingsPath,
    hook_registered: readHookRegistration({ fs, settingsPath, homedir }),
  };
  if (!fs.existsSync(configPath)) {
    return { ...base, installed: false, state: 'missing' };
  }
  try {
    const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
    return {
      ...base,
      installed: true,
      state: config.enable === false ? 'disabled' : 'enabled',
      enable: config.enable !== false,
      scan_validity_days: config.scan_validity_days ?? null,
      repo_root: config.repo_root ?? null,
    };
  } catch {
    return { ...base, installed: true, state: 'corrupt' };
  }
}

/** Unwrap a supabase-js result; a query error aborts the Supabase half. */
function unwrap({ data, error }, what) {
  if (error) throw new Error(`${what} query failed: ${error.message || error}`);
  return data;
}

async function fetchConfigRow(supabase) {
  const row = unwrap(
    await supabase.from('config').select('monitoring_enabled, threshold').eq('id', 1).maybeSingle(),
    'config'
  );
  if (!row) return null;
  return { monitoring_enabled: row.monitoring_enabled !== false, threshold: row.threshold ?? null };
}

async function fetchItemCounts(supabase) {
  // Head-count per status (not a row fetch): PostgREST caps unpaginated
  // selects at 1000 rows, which would silently understate large fleets.
  const counts = {};
  let total = 0;
  for (const status of HEATMAP_STATUSES) {
    const { count, error } = await supabase.from('items')
      .select('id', { count: 'exact', head: true })
      .eq('heatmap_status', status);
    if (error) throw new Error(`Supabase read failed (items ${status}): ${error.message || error}`);
    counts[status] = count ?? 0;
    total += counts[status];
  }
  return { counts, total };
}

/**
 * Fleet-wide stranded count, independent of the recent-runs page — a stranded
 * 'running' row older than the newest --limit runs must still be surfaced
 * (busy systems are exactly where strands accumulate).
 */
async function fetchStrandedCount(supabase, now) {
  const cutoff = new Date(now().getTime() - STRANDED_AFTER_MS).toISOString();
  const { count, error } = await supabase.from('scan_runs')
    .select('id', { count: 'exact', head: true })
    .eq('status', 'running')
    .lt('started_at', cutoff);
  if (error) throw new Error(`Supabase read failed (stranded runs): ${error.message || error}`);
  return count ?? 0;
}

async function fetchRecentRuns(supabase, limit) {
  const rows = unwrap(
    await supabase.from('scan_runs')
      .select('id, item_id, status, started_at, completed_at')
      .order('started_at', { ascending: false })
      .limit(limit),
    'scan_runs'
  );
  return rows || [];
}

/** Join-free name lookup: second query keyed by the runs' item_id list. */
async function fetchItemNames(supabase, runs) {
  const itemIds = [...new Set(runs.map(run => run.item_id).filter(Boolean))];
  if (itemIds.length === 0) return new Map();
  const rows = unwrap(await supabase.from('items').select('id, name').in('id', itemIds), 'item names') || [];
  return new Map(rows.map(row => [row.id, row.name]));
}

async function fetchScannerRows(supabase, runIds) {
  if (runIds.length === 0) return [];
  const rows = unwrap(
    await supabase.from('scan_run_scanners')
      .select('scan_run_id, scanner_source, status')
      .in('scan_run_id', runIds),
    'scan_run_scanners'
  );
  return rows || [];
}

function isStranded(run, nowMs) {
  return run.status === 'running' && nowMs - Date.parse(run.started_at) > STRANDED_AFTER_MS;
}

function summarizeRuns({ runs, nameById, limit, now, strandedTotal }) {
  const counts = {};
  for (const run of runs) counts[run.status] = (counts[run.status] || 0) + 1;
  const nowMs = now().getTime();
  // Fleet-wide head-count wins over the page-local filter; keep the page
  // check as a floor so a null count can never hide a visibly stranded row.
  const strandedOnPage = runs.filter(run => isStranded(run, nowMs)).length;
  const strandedCount = Math.max(strandedTotal ?? 0, strandedOnPage);
  return {
    limit,
    found: runs.length,
    counts,
    recent: runs.slice(0, RECENT_LINES_SHOWN).map(run => ({
      started_at: run.started_at,
      status: run.status,
      item_name: nameById.get(run.item_id) ?? run.item_id ?? '(unknown item)',
    })),
    stranded: { count: strandedCount, remedy: strandedCount > 0 ? STRANDED_REMEDY : null },
  };
}

/**
 * Latest status per scanner_source: runs are newest-first, so the earliest
 * run index (in that order) carrying a row for a source wins.
 */
function summarizeScanners(rows, runIds) {
  const runOrder = new Map(runIds.map((id, i) => [id, i]));
  // Own-keys only: a scanner_source named like an Object.prototype member
  // ('constructor', 'toString', …) must not vanish via inherited-`in` hits.
  const summary = { latest: Object.create(null), unreachable: 0, skipped_missing_credential: 0 };
  const bestRank = new Map();
  for (const row of rows) {
    if (row.status === 'unreachable') summary.unreachable += 1;
    if (row.status === 'skipped_missing_credential') summary.skipped_missing_credential += 1;
    const rank = runOrder.has(row.scan_run_id) ? runOrder.get(row.scan_run_id) : Infinity;
    if (!(row.scanner_source in summary.latest) || rank < bestRank.get(row.scanner_source)) {
      summary.latest[row.scanner_source] = row.status;
      bestRank.set(row.scanner_source, rank);
    }
  }
  return { ...summary, latest: { ...summary.latest } };
}

async function fetchSupabaseSections({ supabase, limit, now }) {
  const config = await fetchConfigRow(supabase);
  const items = await fetchItemCounts(supabase);
  const runs = await fetchRecentRuns(supabase, limit);
  const strandedTotal = await fetchStrandedCount(supabase, now);
  const nameById = await fetchItemNames(supabase, runs);
  const runIds = runs.map(run => run.id);
  const scannerRows = await fetchScannerRows(supabase, runIds);
  return {
    config,
    items,
    runs: summarizeRuns({ runs, nameById, limit, now, strandedTotal }),
    scanners: summarizeScanners(scannerRows, runIds),
  };
}

/** §3 two-switch rule: effective enforcement = local enable AND monitoring_enabled. */
function twoSwitchDisagreement(localHooks, config) {
  return Boolean(config && localHooks.installed && localHooks.state !== 'corrupt'
    && localHooks.enable !== config.monitoring_enabled);
}

function hooksReportLines(hooks) {
  const lines = ['Hooks'];
  if (!hooks.installed) {
    lines.push(`  Config:     not installed (${hooks.config_path} missing) — run agentvetter setup-agent-hooks`);
  } else if (hooks.state === 'corrupt') {
    lines.push(`  Config:     ${hooks.config_path} is unparseable — the hook treats this as tampering and DENIES; delete it and re-run agentvetter setup-agent-hooks`);
  } else {
    lines.push(`  Config:     ${hooks.config_path} — enable=${hooks.enable}, scan_validity_days=${hooks.scan_validity_days}, repo_root=${hooks.repo_root}`);
  }
  lines.push(hooks.hook_registered
    ? `  PreToolUse: registered in ${hooks.settings_path}`
    : `  PreToolUse: not registered at user level (${hooks.settings_path}) — a project-scope .claude/settings.json may still register it; run agentvetter setup-agent-hooks`);
  if (!hooks.installed && hooks.hook_registered) {
    lines.push('  WARNING: hook is registered but config.json is missing — the guard treats this as tampering and DENIES all matched tools until agentvetter setup-agent-hooks is re-run.');
  }
  return lines;
}

function configReportLines(config, localHooks) {
  const lines = [config
    ? `  Supabase:   monitoring_enabled=${config.monitoring_enabled}, threshold=${config.threshold}`
    : '  Supabase:   config row missing — monitoring_enabled unknown (run agentvetter setup)'];
  if (twoSwitchDisagreement(localHooks, config)) {
    lines.push(`  WARNING: two-switch disagreement — local enable=${localHooks.enable}, Supabase monitoring_enabled=${config.monitoring_enabled}; effective enforcement is their AND, so the guard is currently NOT blocking.`);
  }
  return lines;
}

function itemsReportLines(items) {
  const summary = items.total === 0
    ? '  no items recorded yet — run agentvetter scan'
    : `  ${HEATMAP_STATUSES.map(s => `${s}=${items.counts[s]}`).join(' ')} (total ${items.total})`;
  return ['', 'Items (heatmap_status)', summary];
}

function runsReportLines(runs) {
  const lines = ['', `Recent scan runs (last ${runs.limit} requested, ${runs.found} found)`];
  if (runs.found === 0) {
    lines.push('  no scan runs recorded yet — run agentvetter scan');
  } else {
    lines.push(`  ${Object.entries(runs.counts).map(([status, n]) => `${status}=${n}`).join(' ')}`);
    for (const run of runs.recent) lines.push(`  ${run.started_at}  ${run.status}  ${run.item_name}`);
  }
  if (runs.stranded.count > 0) {
    lines.push(`  STRANDED: ${runs.stranded.count} running run(s) older than 30 minutes (likely Modal timeout) — remedy: ${runs.stranded.remedy}`);
  }
  return lines;
}

function scannersReportLines(scanners) {
  const lines = ['', 'Scanners (latest status per source across those runs)'];
  const sources = Object.keys(scanners.latest).sort();
  if (sources.length === 0) lines.push('  no scanner rows for these runs');
  for (const source of sources) lines.push(`  ${source}: ${scanners.latest[source]}`);
  lines.push(`  unreachable=${scanners.unreachable} skipped_missing_credential=${scanners.skipped_missing_credential}`);
  return lines;
}

function supabaseReportLines(remote, localHooks) {
  return [
    ...configReportLines(remote.config, localHooks),
    ...itemsReportLines(remote.items),
    ...runsReportLines(remote.runs),
    ...scannersReportLines(remote.scanners),
  ];
}

function degradedReportLines(supabaseError) {
  return [
    '',
    `Supabase unreachable — set SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY (see .env.example). Detail: ${supabaseError}`,
    'Showing local hooks state only.',
  ];
}

function buildHooksPayload(localHooks, config) {
  return {
    ...localHooks,
    supabase_monitoring_enabled: config ? config.monitoring_enabled : null,
    supabase_threshold: config ? config.threshold : null,
    two_switch_disagreement: twoSwitchDisagreement(localHooks, config),
  };
}

function buildPayload(localHooks, remote, supabaseError) {
  const config = remote ? remote.config : null;
  return {
    hooks: buildHooksPayload(localHooks, config),
    items: remote ? remote.items : null,
    runs: remote ? remote.runs : null,
    scanners: remote ? remote.scanners : null,
    supabase: remote ? { reachable: true } : { reachable: false, error: supabaseError },
  };
}

/** Injectable seams with production defaults (mirrors setupAgentHooks.js). */
function resolveOptions(opts) {
  return {
    json: false,
    limit: DEFAULT_LIMIT,
    supabase: null,           // pre-built client (tests); default resolves via getClient
    getClient: getSupabase,   // may throw when SUPABASE_URL/key are unset — degraded path
    fs: defaultFs,
    homedir: os.homedir(),
    now: () => new Date(),
    log: (msg) => console.log(msg),
    ...opts,
  };
}

/**
 * Run the read-only monitoring report. Returns the machine-readable payload
 * ({hooks, items, runs, scanners, supabase}) that --json prints verbatim.
 */
export async function runStatus(opts = {}) {
  const { json, limit: rawLimit, supabase, getClient, fs, homedir, now, log } = resolveOptions(opts);
  const limit = parseLimit(rawLimit); // throws BEFORE any I/O on invalid input (GWT 3)

  const localHooks = readLocalHooks({ fs, homedir });

  let remote = null;
  let supabaseError = null;
  try {
    remote = await fetchSupabaseSections({ supabase: supabase || getClient(), limit, now });
  } catch (err) {
    supabaseError = err.message || String(err); // degrade — never hard-fail observability
  }

  const payload = buildPayload(localHooks, remote, supabaseError);
  if (json) {
    log(JSON.stringify(payload)); // ONE machine-readable object, nothing else
    return payload;
  }

  const lines = ['[status] AgentVetter monitoring (read-only)', '', ...hooksReportLines(localHooks)];
  lines.push(...(remote ? supabaseReportLines(remote, localHooks) : degradedReportLines(supabaseError)));
  for (const line of lines) log(line);
  return payload;
}
