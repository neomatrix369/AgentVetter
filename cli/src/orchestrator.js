import { ensureSchema } from './ensureSchema.js';
import { getSupabase } from './supabaseClient.js';
import { hashLocalPath } from './hash.js';
import { spawnScanSandbox } from './modalClient.js';
import { runRoute } from './router.js';
import { runBatchJudgement } from './judgePanel.js';
import {
  buildCoverageLedger,
  formatCoverageLedger,
} from './coverageLedger.js';
import { evidenceReportForWorkdir } from './evidenceVerify.js';
import {
  expectedScannersFor,
  formatScannerInventory,
  mergeScannerInventory,
} from './scannerInventory.js';

function judgePanelEnvEnabled() {
  return process.env.AGENTVETTER_JUDGE_PANEL === '1';
}

async function mapWithConcurrency(items, limit, fn) {
  const results = new Array(items.length);
  let i = 0;
  async function worker() {
    while (i < items.length) {
      const idx = i++;
      results[idx] = await fn(items[idx], idx).catch(err => ({ error: err.message }));
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
  return results;
}

function normalizeIdentifier(targetPath) {
  return String(targetPath || '').replace(/^\.\//, '').replace(/\/+$/, '');
}

async function contentHashFor(target, identifier) {
  if (target.avail === 'source_on_disk') return hashLocalPath(target.target);
  return 'pending:' + identifier;
}

function itemNameFor(target, identifier) {
  if (target.name) return target.name;
  return identifier.split('/').pop() || identifier;
}

async function updateItemRow(supabase, id, fields) {
  const { data, error } = await supabase
    .from('items')
    .update({ ...fields, updated_at: new Date().toISOString() })
    .eq('id', id)
    .select()
    .single();
  if (error) throw error;
  return data;
}

async function findLatestByIdentifier(supabase, identifier) {
  const { data } = await supabase
    .from('items')
    .select('*')
    .eq('identifier', identifier)
    .order('updated_at', { ascending: false })
    .limit(1);
  return Array.isArray(data) ? data[0] : null;
}

async function upsertItem(supabase, target) {
  const identifier = target.identifier || normalizeIdentifier(target.target);
  const name = itemNameFor(target, identifier);
  const contentHash = await contentHashFor(target, identifier);
  // A placeholder hash marks an item that has never completed a scan: never a cache hit.
  const isPlaceholder = contentHash.startsWith('pending:');
  const { data: byHash } = isPlaceholder
    ? { data: null }
    : await supabase.from('items').select('*').eq('content_hash', contentHash).maybeSingle();
  if (byHash) {
    // Refresh display name even on content-hash hits (e.g. card-naming contract changes).
    if (byHash.name === name) return { item: byHash, cached: true };
    return { item: await updateItemRow(supabase, byHash.id, { name }), cached: true };
  }

  // Reuse the latest row for this path so the live heatmap does not accumulate
  // duplicate identifier rows when content_hash changes between scans.
  const existing = await findLatestByIdentifier(supabase, identifier);
  if (existing) {
    // Keep the stored hash until a scan succeeds. The guard compares disk content to
    // this hash, so writing it now would let edited content inherit the old verdict.
    const updated = await updateItemRow(supabase, existing.id, { name });
    return { item: updated, cached: false, pendingHash: contentHash };
  }

  // Insert a placeholder hash: the real hash is committed only after a successful scan,
  // so a failed first scan is retried on the next run instead of looking cached.
  const { data: inserted, error } = await supabase.from('items').insert({
    type: target.type, name,
    identifier, content_hash: 'pending:' + identifier,
    install_locus: target.locus || 'unknown', source_availability: target.avail || 'unknown'
  }).select().single();
  if (error) throw error;
  return { item: inserted, cached: false, pendingHash: contentHash };
}

export async function dispatchTarget(supabase, target, { batchId, force, spawnFn }) {
  try {
    const { item, cached, pendingHash } = await upsertItem(supabase, target);
    if (cached && !force) {
      console.log(`[skip] ${target.target} — content unchanged since last scan`);
      return { target: target.target, scanRunId: null };
    }
    const { data: run, error: runError } = await supabase.from('scan_runs').insert({
      item_id: item.id, batch_id: batchId, status: 'running'
    }).select().single();
    if (runError) throw runError;

    try {
      await spawnFn({
        target: target.target,
        itemType: target.type,
        itemId: item.id,
        scanRunId: run.id,
        packPath: target.packPath || null,
      });
      // The scan finished cleanly, so the new content is now the one with a verdict.
      if (pendingHash) await updateItemRow(supabase, item.id, { content_hash: pendingHash });
      return { target: target.target, scanRunId: run.id };
    } catch (err) {
      console.error(`[error] sandbox failed for ${target.target}: ${err.message}`);
      await supabase.from('scan_runs').update({ status: 'failed', completed_at: new Date().toISOString() }).eq('id', run.id);
      await supabase.rpc('agentvetter_rollup_item', { p_item_id: item.id });
      return { target: target.target, scanRunId: run.id, error: err.message };
    }
  } catch (err) {
    const message = err.message || String(err);
    console.error(`[error] scan dispatch failed for ${target.target}: ${message}`);
    return { target: target.target, scanRunId: null, error: message };
  }
}

function assertPositiveConcurrency(concurrency) {
  if (!Number.isInteger(concurrency) || concurrency < 1) {
    throw new Error('--concurrency must be a positive integer');
  }
}

async function createScanBatch(supabase, targets, concurrency) {
  const { data: batch, error } = await supabase.from('scan_batches').insert({
    source_path: targets.map(t => t.target).join(','), item_count: targets.length, concurrency_limit: concurrency
  }).select().single();
  if (error) throw new Error(`Failed to create scan batch: ${error.message || error.code || 'unknown error'}`);
  return batch.id;
}

async function fetchScannerRows(supabase, scanRunId) {
  const { data, error } = await supabase
    .from('scan_run_scanners')
    .select('scanner_source, status')
    .eq('scan_run_id', scanRunId);
  if (error) throw error;
  return Array.isArray(data) ? data : [];
}

/**
 * Print coverage ledger for a package target after scan inventory is known.
 * Pre-scan (not dispatched / dry-discover) passes empty scannerRows → not_started.
 * Post-scan passes scan_run_scanners rows → completed/failed/skipped/timed_out.
 * Ledger rollup (fully covered / partly covered / unsupported or unscanned) is
 * operator-facing honesty — distinct from scan_run.status and scanner inventory
 * rollup (ADR-0009 / inventory fully successful). Do not map one onto the other.
 */
function printCoverageLedgerForPackage(target, scannerRows = []) {
  if (target.type !== 'package') return;
  const workdir = target.target;
  if (!workdir) return;
  const ledger = buildCoverageLedger(workdir, scannerRows);
  if (!ledger.length) return;
  const label = target.identifier || target.target;
  console.log(formatCoverageLedger(ledger, { label }));
}

function printEvidenceForTarget(target, revealSecrets) {
  if (target.type !== 'skill' && target.type !== 'mcp_server') return;
  const workdir = target.target;
  if (!workdir) return;
  console.log(evidenceReportForWorkdir(workdir, {
    label: target.identifier || target.target,
    revealSecrets,
  }));
}

async function printInventoryForOutcome(supabase, target, outcome, revealSecrets) {
  const label = target.identifier || target.target;
  if (!outcome.scanRunId) {
    const inventory = mergeScannerInventory(expectedScannersFor(target.type), []);
    console.log(formatScannerInventory(inventory, { label: `${label} (not dispatched)` }));
    printCoverageLedgerForPackage(target, []);
    printEvidenceForTarget(target, revealSecrets);
    return;
  }
  try {
    const rows = await fetchScannerRows(supabase, outcome.scanRunId);
    const inventory = mergeScannerInventory(expectedScannersFor(target.type), rows);
    console.log(formatScannerInventory(inventory, { label }));
    printCoverageLedgerForPackage(target, rows);
    printEvidenceForTarget(target, revealSecrets);
  } catch (err) {
    console.warn(`[warn] could not load scanner inventory for ${label}: ${err.message}`);
  }
}

async function printInventoriesForOutcomes(supabase, targets, outcomes, revealSecrets) {
  for (let i = 0; i < targets.length; i++) {
    await printInventoryForOutcome(supabase, targets[i], outcomes[i], revealSecrets);
  }
}

async function routeBatchSafely(routeFn, batchId) {
  try {
    await routeFn(batchId);
  } catch (err) {
    console.warn(`[warn] auto-route failed for batch ${batchId}: ${err.message}`);
  }
}

/** Soft-fail post-route judge panel — only when AGENTVETTER_JUDGE_PANEL=1 (default off). */
async function judgeBatchSafely(judgeFn, batchId) {
  try {
    await judgeFn(batchId);
  } catch (err) {
    console.warn(`[warn] auto-judge-panel failed for batch ${batchId}: ${err.message}`);
  }
}

/** ADR-0016 auto-route always; opt-in soft-fail panel only when env set. */
async function runPostScanJudgement(routeFn, judgeFn, batchId) {
  await routeBatchSafely(routeFn, batchId);
  if (judgePanelEnvEnabled()) await judgeBatchSafely(judgeFn, batchId);
}

function resolveScanDeps(opts = {}) {
  return {
    concurrency: opts.concurrency ?? 5,
    force: opts.force ?? false,
    revealSecrets: opts.revealSecrets ?? false,
    ensureSchemaFn: opts.ensureSchemaFn || ensureSchema,
    getSupabaseFn: opts.getSupabaseFn || getSupabase,
    spawnFn: opts.spawnFn || spawnScanSandbox,
    routeFn: opts.routeFn || runRoute,
    judgeFn: opts.judgeFn || runBatchJudgement,
  };
}

function scanResultFromOutcomes(batchId, outcomes) {
  const failures = outcomes.filter(outcome => outcome.error);
  return {
    failures,
    result: {
      batch_id: batchId,
      scan_run_ids: outcomes.map(outcome => outcome.scanRunId).filter(Boolean),
      failed_targets: failures.map(({ target, error }) => ({ target, error })),
    },
  };
}

export async function runScan(targets, opts = {}) {
  const {
    concurrency, force, revealSecrets,
    ensureSchemaFn, getSupabaseFn, spawnFn, routeFn, judgeFn,
  } = resolveScanDeps(opts);

  assertPositiveConcurrency(concurrency);
  await ensureSchemaFn();
  const supabase = getSupabaseFn();
  const batchId = await createScanBatch(supabase, targets, concurrency);

  const outcomes = await mapWithConcurrency(
    targets,
    concurrency,
    target => dispatchTarget(supabase, target, { batchId, force, spawnFn }),
  );

  const { failures, result } = scanResultFromOutcomes(batchId, outcomes);
  console.log(JSON.stringify(result, null, 2));

  await printInventoriesForOutcomes(supabase, targets, outcomes, revealSecrets);
  await runPostScanJudgement(routeFn, judgeFn, batchId);

  if (failures.length) {
    throw new Error(`${failures.length} target scan dispatch failure(s); inspect failed_targets output`);
  }
  return result;
}
