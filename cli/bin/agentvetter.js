#!/usr/bin/env node
import { Command } from 'commander';
import { discoverTargets, VALID_TYPE_FILTERS } from '../src/discovery.js';
import { ensureSchema } from '../src/ensureSchema.js';
import { loadEnv } from '../src/loadEnv.js';
import { runScan } from '../src/orchestrator.js';
import { runRoute } from '../src/router.js';
import { runBatchJudgement } from '../src/judgePanel.js';
import {
  buildCoverageLedger,
  formatCoverageLedger,
} from '../src/coverageLedger.js';
import { evidenceReportForWorkdir } from '../src/evidenceVerify.js';
import {
  formatScannerInventory,
  inventoryForNotRun,
} from '../src/scannerInventory.js';
import { runSetupAgentHooks } from '../src/setupAgentHooks.js';
import { runStatus } from '../src/statusCommand.js';

function printOncePerWorkdir(list, typeOk, printer) {
  const seen = new Set();
  for (const target of list) {
    if (!typeOk(target)) continue;
    const workdir = target.target;
    if (!workdir || seen.has(workdir)) continue;
    seen.add(workdir);
    printer(target, workdir);
  }
}

function printDryDiscoverCoverage(list) {
  printOncePerWorkdir(list, (t) => t.type === 'package', (target, workdir) => {
    const ledger = buildCoverageLedger(workdir, []);
    if (!ledger.length) return;
    console.log(formatCoverageLedger(ledger, {
      label: `${target.identifier || workdir} (pre-scan)`,
    }));
  });
}

function printDryDiscoverEvidence(list, revealSecrets) {
  printOncePerWorkdir(
    list,
    (t) => t.type === 'skill' || t.type === 'mcp_server',
    (target, workdir) => {
      console.log(evidenceReportForWorkdir(workdir, {
        label: `${target.identifier || workdir} (pre-scan)`,
        revealSecrets,
      }));
    },
  );
}

loadEnv();

const program = new Command();
program.name('agentvetter').description('Scan AI skills and MCP servers for security issues');

program
  .command('setup')
  .description('Apply db/schema.sql to Supabase if tables are missing (uses SUPABASE_DB_URL)')
  .option('--force', 're-apply schema even if probe says ready', false)
  .action(async (opts) => {
    try {
      const result = await ensureSchema({ force: Boolean(opts.force) });
      console.log(JSON.stringify(result));
    } catch (err) {
      console.error(err.message || err);
      process.exitCode = 1;
    }
  });

function printZeroArtifactOutcome(targets, opts) {
  const label = Array.isArray(targets) && targets.length
    ? targets.join(', ')
    : opts.targets;
  console.log(`No skill or MCP artifacts found in: ${label}`);
  const typeHint = opts.type === 'mcp' ? 'mcp_server' : (opts.type || null);
  console.log(formatScannerInventory(inventoryForNotRun(typeHint), { label }));
}

function requireScanTargets(targets, opts, list) {
  if (list.length > 0) return;
  const hadExplicit = (Array.isArray(targets) && targets.length > 0) || Boolean(opts.targets);
  if (hadExplicit) {
    printZeroArtifactOutcome(targets, opts);
    return;
  }
  throw new Error('No targets found. Pass a path/URL, or run inside a folder with agent-installed skills/MCP configs.');
}

function parseScanOpts(opts) {
  const concurrency = Number(opts.concurrency);
  if (!Number.isInteger(concurrency) || concurrency < 1) {
    throw new Error('--concurrency must be a positive integer');
  }
  if (opts.type && !VALID_TYPE_FILTERS.includes(opts.type)) {
    throw new Error(`--type must be one of: ${VALID_TYPE_FILTERS.join(', ')}`);
  }
  return { concurrency, typeFilter: opts.type || null };
}

async function scanAction(targets, opts) {
  const { concurrency, typeFilter } = parseScanOpts(opts);
  const list = await discoverTargets({
    targets, targetsFile: opts.targets, useDefaults: opts.defaults !== false, typeFilter,
  });
  if (opts.dryDiscover) {
    console.log(JSON.stringify(list, null, 2));
    printDryDiscoverCoverage(list);
    printDryDiscoverEvidence(list, Boolean(opts.revealSecrets));
    return;
  }
  if (list.length === 0) {
    requireScanTargets(targets, opts, list);
    return;
  }
  await runScan(list, {
    concurrency,
    force: Boolean(opts.force),
    revealSecrets: Boolean(opts.revealSecrets),
  });
}

program
  .command('scan', { isDefault: true })
  .description('Discover and scan AI skills/MCP servers (default command)')
  .argument('[targets...]', 'paths, git URLs, or live MCP endpoints; omit for machine defaults')
  .option('--targets <file>', 'JSON file with a "targets" array')
  .option('--concurrency <n>', 'max concurrent sandboxes', '5')
  .option('--force', 're-scan even if content hash is unchanged')
  .option('--no-defaults', 'error instead of scanning machine defaults on empty args')
  .option('--dry-discover', 'print discovered targets and exit, spawn nothing')
  .option('--reveal-secrets', 'show secret-like tokens in evidence/logs (masked by default)', false)
  .option('--type <type>', `restrict discovery to a single artifact category (${VALID_TYPE_FILTERS.join('|')})`)
  .action(async (targets, opts) => {
    try {
      await scanAction(targets, opts);
    } catch (err) {
      console.error(err.message || err);
      process.exitCode = 1;
    }
  });

program
  .command('route')
  .description('Run tiered model router for a completed batch (SIE + optional Model Studio)')
  .requiredOption('--batch-id <id>', 'batch_id to route')
  .option('--sie-model <model>', 'SIE model name (overrides SIE_MODEL env)')
  .option('--model-studio-model <model>', 'Model Studio model name (overrides MODEL_STUDIO_MODEL env)')
  .action(async (opts) => {
    try {
      await runRoute(opts.batchId, {
        sieModel: opts.sieModel,
        modelStudioModel: opts.modelStudioModel,
      });
    } catch (err) {
      console.error(err.message || err);
      process.exitCode = 1;
    }
  });

program
  .command('judge')
  .description(
    'Run SIE judge panel + final judge for a completed batch (slice 67; additive to ADR-0016 route)',
  )
  .requiredOption('--batch-id <id>', 'batch_id to judge')
  .action(async (opts) => {
    try {
      const { panel_runs: panelRuns } = await runBatchJudgement(opts.batchId);
      console.log(JSON.stringify({ batch_id: opts.batchId, panel_runs: panelRuns.length }, null, 2));
    } catch (err) {
      console.error(err.message || err);
      process.exitCode = 1;
    }
  });

program
  .command('setup-agent-hooks')
  .description('Install Claude Code PreToolUse hooks, /av-* skills (tw-* aliases), and ~/.agentvetter config')
  .option('--with-demo', 'also install and scan demo artifacts', false)
  .action(async (opts) => {
    try {
      await runSetupAgentHooks({ withDemo: Boolean(opts.withDemo) });
    } catch (err) {
      console.error(err.message || err);
      process.exitCode = 1;
    }
  });

program
  .command('status')
  .description('Show AgentVetter agent-hook + scan/dispatch health (read-only)')
  .option('--json', 'print one machine-readable JSON object instead of prose', false)
  .option('--limit <n>', 'recent scan runs to inspect (1-200)', '20')
  .action(async (opts) => {
    try {
      await runStatus({ json: Boolean(opts.json), limit: opts.limit });
    } catch (err) {
      console.error(err.message || err);
      process.exitCode = 1;
    }
  });

program.parseAsync(process.argv);
