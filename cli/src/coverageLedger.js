/**
 * Language/ecosystem coverage ledger (slice 65).
 *
 * Discovery is marker-driven: only ecosystems whose manifests exist are listed.
 * Scanners are reused from the Wave P / Cargo Audit registry — never invented.
 */
import { existsSync, readdirSync, statSync } from 'node:fs';
import path from 'node:path';

/** Canonical action statuses for ledger rows (GWT-65.4). */
export const ACTION_STATUSES = new Set([
  'not_started',
  'running',
  'completed',
  'failed',
  'timed_out',
  'skipped',
]);

const SKIP_DIRS = new Set(['node_modules', '.git', 'venv', '.venv', '__pycache__', 'target', 'dist']);

/**
 * Marker → ecosystem catalogue. Rows are only emitted when ≥1 marker is found.
 * `scanners` lists existing adapters that can cover the ecosystem (reuse-first).
 * `unsupported_by` names known gaps that stay explicit even when another scanner completes.
 */
const ECOSYSTEM_CATALOGUE = [
  {
    ecosystem: 'Node/npm',
    language: 'JavaScript',
    markers: ['package.json', 'package-lock.json', 'pnpm-lock.yaml', 'yarn.lock'],
    scanners: ['DepShield', 'Snyk', 'Ossprey'],
    unsupported_by: [],
  },
  {
    ecosystem: 'Python',
    language: 'Python',
    markers: ['pyproject.toml', 'requirements.txt', 'Pipfile', 'poetry.lock'],
    scanners: ['DepShield', 'Snyk', 'Ossprey'],
    unsupported_by: [],
  },
  {
    ecosystem: 'Java/Maven-Gradle',
    language: 'Java',
    markers: ['pom.xml', 'build.gradle', 'build.gradle.kts'],
    scanners: ['Snyk'],
    unsupported_by: ['DepShield (npm+PyPI manifests only)'],
  },
  {
    ecosystem: 'Go',
    language: 'Go',
    markers: ['go.mod', 'go.sum'],
    scanners: ['Snyk'],
    unsupported_by: ['DepShield (npm+PyPI manifests only)'],
  },
  {
    ecosystem: 'Rust/Cargo',
    language: 'Rust',
    markers: ['Cargo.toml', 'Cargo.lock'],
    scanners: ['Cargo Audit'],
    unsupported_by: [
      'Snyk `snyk test` (no Rust/Cargo SCA)',
      'DepShield (package.json / requirements.txt only)',
    ],
  },
  {
    ecosystem: 'Ruby/Bundler',
    language: 'Ruby',
    markers: ['Gemfile', 'Gemfile.lock'],
    scanners: ['Snyk'],
    unsupported_by: ['DepShield (npm+PyPI manifests only)'],
  },
  {
    ecosystem: 'PHP/Composer',
    language: 'PHP',
    markers: ['composer.json', 'composer.lock'],
    scanners: ['Snyk'],
    unsupported_by: ['DepShield (npm+PyPI manifests only)'],
  },
  {
    ecosystem: 'Swift/SPM',
    language: 'Swift',
    markers: ['Package.swift', 'Package.resolved'],
    scanners: ['Snyk'],
    unsupported_by: ['DepShield (npm+PyPI manifests only)'],
  },
];

function safeStat(target) {
  try {
    return statSync(target);
  } catch {
    return null;
  }
}

function safeReaddir(dir) {
  try {
    return readdirSync(dir, { withFileTypes: true });
  } catch {
    return null;
  }
}

function collectWalkEntry(dir, entry, stack, names) {
  if (entry.isDirectory()) {
    if (!SKIP_DIRS.has(entry.name)) stack.push(path.join(dir, entry.name));
    return;
  }
  if (entry.isFile()) names.push(entry.name);
}

function walkFilenames(root) {
  const names = [];
  if (!root || !existsSync(root)) return names;
  const rootStat = safeStat(root);
  if (!rootStat?.isDirectory()) return names;

  const stack = [root];
  while (stack.length) {
    const dir = stack.pop();
    const entries = safeReaddir(dir);
    if (!entries) continue;
    for (const entry of entries) collectWalkEntry(dir, entry, stack, names);
  }
  return names;
}

/**
 * Discover ecosystems present under *workdir* (marker-driven; never a closed language dump).
 * @param {string} workdir
 * @returns {{ ecosystem: string, language: string, volume: number, markers_found: string[],
 *   scanners: string[], unsupported_by: string[] }[]}
 */
export function discoverEcosystems(workdir) {
  const filenames = walkFilenames(workdir);
  if (!filenames.length) return [];
  const counts = new Map();
  for (const name of filenames) {
    counts.set(name, (counts.get(name) || 0) + 1);
  }

  const found = [];
  for (const entry of ECOSYSTEM_CATALOGUE) {
    const markersFound = entry.markers.filter((m) => counts.has(m));
    if (!markersFound.length) continue;
    const volume = markersFound.reduce((sum, m) => sum + (counts.get(m) || 0), 0);
    found.push({
      ecosystem: entry.ecosystem,
      language: entry.language,
      volume,
      markers_found: markersFound,
      scanners: [...entry.scanners],
      unsupported_by: [...entry.unsupported_by],
    });
  }
  return found;
}

/** Inventory / scan_run status → ledger action status (GWT-65.4). */
const STATUS_TO_ACTION = new Map([
  ['completed', 'completed'],
  ['running', 'running'],
  ['timed_out', 'timed_out'],
  ['timeout', 'timed_out'],
  ['failed', 'failed'],
  ['unreachable', 'failed'],
  ['interrupted', 'failed'],
  ['skipped', 'skipped'],
  ['skipped_missing_credential', 'skipped'],
  ['not_applicable', 'skipped'],
  // Scanner needs setup (e.g. missing credential): shown as skipped, not silently not_started.
  ['needs_setup', 'skipped'],
]);

/**
 * Map scan_run_scanners / inventory status → ledger action status.
 * @param {string|null|undefined} status
 * @returns {string}
 */
export function mapScannerStatusToAction(status) {
  const raw = String(status || 'not_run');
  return STATUS_TO_ACTION.get(raw) || 'not_started';
}

function pickBestScanner(ecosystemScanners, bySource) {
  const preference = ['completed', 'running', 'timed_out', 'failed', 'skipped', 'not_started'];
  let best = null;
  for (const name of ecosystemScanners) {
    const action = mapScannerStatusToAction(bySource.get(name));
    if (!best) {
      best = { scanner: name, status: action };
      continue;
    }
    if (preference.indexOf(action) < preference.indexOf(best.status)) {
      best = { scanner: name, status: action };
    }
  }
  if (best) return best;
  return { scanner: null, status: 'skipped' };
}

/**
 * Build per-ecosystem coverage rows for *workdir*.
 * @param {string} workdir
 * @param {{ scanner_source?: string, scanner?: string, status: string }[]} [scannerRows]
 */
export function buildCoverageLedger(workdir, scannerRows = []) {
  const ecosystems = discoverEcosystems(workdir);
  const bySource = new Map();
  for (const row of scannerRows || []) {
    const name = row.scanner_source || row.scanner;
    if (!name) continue;
    bySource.set(name, row.status || 'not_run');
  }

  return ecosystems.map((eco) => {
    const { scanner, status } = pickBestScanner(eco.scanners, bySource);
    const hasRows = bySource.size > 0;
    let actionStatus = status;
    let reason = null;
    if (!hasRows) {
      actionStatus = 'not_started';
    } else if (!eco.scanners.length) {
      actionStatus = 'skipped';
      reason = `No applicable scanner registered for ${eco.ecosystem}`;
    } else if (actionStatus !== 'completed' && actionStatus !== 'running') {
      const gaps = eco.unsupported_by.length
        ? eco.unsupported_by.join('; ')
        : 'no completed scanner for this ecosystem';
      reason = scanner
        ? `${scanner} → ${actionStatus}; ${gaps}`
        : gaps;
    }

    const unsupported = [...eco.unsupported_by];
    if (actionStatus !== 'completed' && !unsupported.length) {
      unsupported.push(`${eco.ecosystem} not covered by a completed scanner`);
    }

    return {
      ecosystem: eco.ecosystem,
      language: eco.language,
      volume: eco.volume,
      markers_found: eco.markers_found,
      scanner,
      status: actionStatus,
      coverage: actionStatus === 'completed' ? 'partial_or_full' : 'none',
      unsupported_portions: unsupported,
      reason_not_scanned: reason,
    };
  });
}

/**
 * Coverage rollup — never "fully successful" when any ecosystem lacks a completed scan.
 * Operator-facing only; not the same enum as scan_run.status or scanner-inventory
 * rollup (`fully successful` / `partly successful` / `fully failed`).
 * @param {{ status: string }[]} ledger
 */
export function rollupCoverageLedger(ledger) {
  if (!ledger.length) return 'no ecosystems detected';
  const statuses = ledger.map((row) => row.status);
  if (statuses.every((s) => s === 'not_started')) return 'not started';
  const completed = statuses.filter((s) => s === 'completed').length;
  if (completed === statuses.length) return 'fully covered';
  if (completed >= 1) return 'partly covered';
  return 'unsupported or unscanned';
}

/**
 * @param {ReturnType<typeof buildCoverageLedger>} ledger
 * @param {{ label?: string }} [opts]
 */
export function formatCoverageLedger(ledger, opts = {}) {
  const rollup = rollupCoverageLedger(ledger);
  const header = opts.label
    ? `[coverage] ${opts.label} — ${rollup}`
    : `[coverage] ${rollup}`;
  const lines = [header];
  for (const row of ledger) {
    const scanner = row.scanner || '(none)';
    const unsupported = (row.unsupported_portions || []).join('; ') || '—';
    const reason = row.reason_not_scanned ? ` | reason: ${row.reason_not_scanned}` : '';
    lines.push(
      `  ${row.ecosystem} (vol=${row.volume}): scanner=${scanner} status=${row.status}`
      + ` coverage=${row.coverage} unsupported=[${unsupported}]${reason}`,
    );
  }
  return lines.join('\n');
}
