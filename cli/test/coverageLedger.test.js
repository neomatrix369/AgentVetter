/**
 * Tests for cli/src/coverageLedger.js.
 *
 * Author: swami
 * Created: 2026-09-20
 * Scope: GWT-65.1–65.4 ecosystem discovery, scanner reuse, unsupported Cargo,
 *        action-status mapping, coverage rollup honesty;
 *        GWT-72.1–72.4 Rust/Cargo gap scanner formalization (ledger honesty)
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {
  ACTION_STATUSES,
  buildCoverageLedger,
  discoverEcosystems,
  formatCoverageLedger,
  mapScannerStatusToAction,
  rollupCoverageLedger,
} from '../src/coverageLedger.js';

async function withFixture(files, fn) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'av-cov-'));
  try {
    for (const [rel, body] of Object.entries(files)) {
      const full = path.join(root, rel);
      await mkdir(path.dirname(full), { recursive: true });
      await writeFile(full, body, 'utf8');
    }
    await fn(root);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
}

test('GWT-65.1: multi-ecosystem checkout lists Node and Rust with volume', async () => {
  await withFixture(
    {
      'package.json': '{"name":"demo"}',
      'Cargo.toml': '[package]\nname = "demo"\n',
    },
    (root) => {
      // -- Given / When --
      const found = discoverEcosystems(root);

      // -- Then --
      const names = found.map((row) => row.ecosystem).sort();
      assert.deepEqual(names, ['Node/npm', 'Rust/Cargo']);
      assert.ok(found.every((row) => row.volume > 0), 'each ecosystem needs non-zero volume');
    },
  );
});

test('GWT-65.1: discovery is marker-driven — empty tree yields no closed language list', () => {
  // -- Given / When --
  const found = discoverEcosystems('/tmp/agentvetter-no-such-dir-coverage-65');

  // -- Then --
  assert.deepEqual(found, []);
});

test('GWT-65.2: Node ecosystem reuses DepShield/Snyk/Ossprey — no invented scanner', async () => {
  await withFixture({ 'package.json': '{"name":"app"}' }, (root) => {
    // -- Given --
    const scannerRows = [
      { scanner_source: 'DepShield', status: 'completed' },
      { scanner_source: 'Snyk', status: 'completed' },
      { scanner_source: 'Ossprey', status: 'skipped_missing_credential' },
    ];

    // -- When --
    const ledger = buildCoverageLedger(root, scannerRows);
    const node = ledger.find((row) => row.ecosystem === 'Node/npm');

    // -- Then --
    assert.ok(node, 'Node/npm row required');
    assert.equal(node.status, 'completed');
    assert.ok(
      ['DepShield', 'Snyk', 'Ossprey'].includes(node.scanner),
      `unexpected scanner ${node.scanner}`,
    );
    assert.equal(node.coverage, 'partial_or_full');
  });
});

test('GWT-65.3: Cargo-only marks Rust unsupported/skipped when no scanner completed', async () => {
  await withFixture(
    {
      'Cargo.toml': '[package]\nname = "only-rust"\n',
      'Cargo.lock': '# lock\n',
    },
    (root) => {
      // -- Given --
      const scannerRows = [
        { scanner_source: 'Snyk', status: 'not_applicable' },
        { scanner_source: 'DepShield', status: 'not_applicable' },
        { scanner_source: 'Ossprey', status: 'not_applicable' },
        { scanner_source: 'Cargo Audit', status: 'unreachable' },
      ];

      // -- When --
      const ledger = buildCoverageLedger(root, scannerRows);
      const rust = ledger.find((row) => row.ecosystem === 'Rust/Cargo');
      const rollup = rollupCoverageLedger(ledger);

      // -- Then --
      assert.ok(rust, 'Rust/Cargo ledger row required');
      assert.ok(
        ['skipped', 'failed'].includes(rust.status),
        `expected skipped/failed, got ${rust.status}`,
      );
      assert.match(
        rust.reason_not_scanned || '',
        /Snyk|DepShield|Cargo|unsupported|not/i,
      );
      assert.ok(rust.unsupported_portions.length > 0);
      assert.notEqual(rollup, 'fully successful');
      assert.match(formatCoverageLedger(ledger), /Rust\/Cargo/);
      assert.doesNotMatch(formatCoverageLedger(ledger), /fully successful/);
    },
  );
});

test('GWT-65.3: Cargo-only with completed Cargo Audit is covered (reuse, not invent)', async () => {
  await withFixture({ 'Cargo.toml': '[package]\nname = "audited"\n' }, (root) => {
    // -- Given --
    const scannerRows = [
      { scanner_source: 'Cargo Audit', status: 'completed' },
      { scanner_source: 'Snyk', status: 'not_applicable' },
    ];

    // -- When --
    const ledger = buildCoverageLedger(root, scannerRows);
    const rust = ledger.find((row) => row.ecosystem === 'Rust/Cargo');

    // -- Then --
    assert.equal(rust.scanner, 'Cargo Audit');
    assert.equal(rust.status, 'completed');
    assert.ok(
      (rust.unsupported_portions || []).some((p) => /Snyk|DepShield/i.test(p)),
      'Snyk/DepShield gap remains explicit even when Cargo Audit completed',
    );
  });
});

test('GWT-65.4: action statuses are from the canonical set', () => {
  const mapping = [
    ['completed', 'completed'],
    ['running', 'running'],
    ['not_run', 'not_started'],
    ['skipped_missing_credential', 'skipped'],
    ['not_applicable', 'skipped'],
    ['unreachable', 'failed'],
    ['failed', 'failed'],
    ['timed_out', 'timed_out'],
  ];
  for (const [raw, expected] of mapping) {
    assert.equal(mapScannerStatusToAction(raw), expected, raw);
    assert.ok(ACTION_STATUSES.has(expected), expected);
  }
  assert.equal(mapScannerStatusToAction('completed'), 'completed');
  assert.notEqual(mapScannerStatusToAction('failed'), 'completed');
  assert.notEqual(mapScannerStatusToAction('timed_out'), 'completed');
  assert.notEqual(mapScannerStatusToAction('skipped_missing_credential'), 'completed');
});

test('GWT-65.4: mixed outcomes never mark failed/timeout/skipped ecosystem as completed', async () => {
  await withFixture(
    {
      'package.json': '{}',
      'go.mod': 'module example.com/x\n',
    },
    (root) => {
      const ledger = buildCoverageLedger(root, [
        { scanner_source: 'DepShield', status: 'completed' },
        { scanner_source: 'Snyk', status: 'timed_out' },
        { scanner_source: 'Ossprey', status: 'failed' },
      ]);
      const go = ledger.find((row) => row.ecosystem === 'Go');
      assert.ok(go);
      assert.notEqual(go.status, 'completed');
      assert.ok(['failed', 'timed_out', 'skipped'].includes(go.status));
    },
  );
});

test('pre-scan ledger uses not_started when no scanner rows', async () => {
  await withFixture({ 'requirements.txt': 'requests==2.0\n' }, (root) => {
    const ledger = buildCoverageLedger(root, []);
    const py = ledger.find((row) => row.ecosystem === 'Python');
    assert.equal(py.status, 'not_started');
    assert.equal(py.coverage, 'none');
  });
});

test('GWT-72.1: Cargo-only checkout scopes ledger to Rust/Cargo — not Node/Python', async () => {
  await withFixture(
    {
      'Cargo.toml': '[package]\nname = "gap-only"\n',
      'Cargo.lock': '# lock\n',
    },
    (root) => {
      // -- Given / When --
      const found = discoverEcosystems(root);
      const names = found.map((row) => row.ecosystem);

      // -- Then --
      assert.deepEqual(names, ['Rust/Cargo']);
      assert.ok(found[0].volume > 0, 'Rust/Cargo must have non-zero volume');
      assert.ok(!names.includes('Node/npm'), 'must not reimplement Node ecosystem');
      assert.ok(!names.includes('Python'), 'must not reimplement Python ecosystem');
    },
  );
});

test('GWT-72.2: Rust/Cargo reuses named Cargo Audit adapter — no invented scanner', async () => {
  await withFixture({ 'Cargo.toml': '[package]\nname = "reuse"\n' }, (root) => {
    // -- Given / When --
    const found = discoverEcosystems(root);
    const rust = found.find((row) => row.ecosystem === 'Rust/Cargo');

    // -- Then --
    assert.ok(rust, 'Rust/Cargo catalogue row required');
    assert.deepEqual(rust.scanners, ['Cargo Audit']);
    assert.ok(
      !rust.scanners.some((name) => /invented|custom.?rust|llm.?rust/i.test(name)),
      'must not invent a parallel Rust scanner name',
    );
  });
});

test('GWT-72.3: Cargo Audit honesty matrix maps completed/failed/timed_out/unreachable', async () => {
  await withFixture(
    {
      'Cargo.toml': '[package]\nname = "honesty"\n',
      'Cargo.lock': '# lock\n',
    },
    async (root) => {
      const cases = [
        { status: 'completed', expected: 'completed', coverage: 'partial_or_full', rollup: 'fully covered' },
        { status: 'failed', expected: 'failed', coverage: 'none', rollup: 'unsupported or unscanned' },
        { status: 'timed_out', expected: 'timed_out', coverage: 'none', rollup: 'unsupported or unscanned' },
        { status: 'unreachable', expected: 'failed', coverage: 'none', rollup: 'unsupported or unscanned' },
      ];

      for (const row of cases) {
        // -- Given --
        const scannerRows = [{ scanner_source: 'Cargo Audit', status: row.status }];

        // -- When --
        const ledger = buildCoverageLedger(root, scannerRows);
        const rust = ledger.find((entry) => entry.ecosystem === 'Rust/Cargo');
        const rollup = rollupCoverageLedger(ledger);

        // -- Then --
        assert.ok(rust, `Rust/Cargo row required for ${row.status}`);
        assert.equal(rust.scanner, 'Cargo Audit', row.status);
        assert.equal(rust.status, row.expected, `status for ${row.status}`);
        assert.equal(rust.coverage, row.coverage, `coverage for ${row.status}`);
        assert.equal(rollup, row.rollup, `rollup for ${row.status}`);
        if (row.expected === 'completed') {
          assert.equal(rollup, 'fully covered');
        } else {
          assert.notEqual(rollup, 'fully covered', `must not claim full cover on ${row.status}`);
        }
      }
    },
  );
});

test('GWT-72.4: completed Cargo Audit names the tool; Snyk/DepShield gaps stay explicit', async () => {
  await withFixture(
    {
      'Cargo.toml': '[package]\nname = "named"\n',
      'Cargo.lock': '# lock\n',
    },
    (root) => {
      // -- Given --
      const scannerRows = [
        { scanner_source: 'Cargo Audit', status: 'completed' },
        { scanner_source: 'Snyk', status: 'not_applicable' },
        { scanner_source: 'DepShield', status: 'not_applicable' },
      ];

      // -- When --
      const ledger = buildCoverageLedger(root, scannerRows);
      const rust = ledger.find((row) => row.ecosystem === 'Rust/Cargo');
      const formatted = formatCoverageLedger(ledger);

      // -- Then --
      assert.equal(rust.scanner, 'Cargo Audit');
      assert.equal(rust.status, 'completed');
      assert.equal(rust.coverage, 'partial_or_full');
      assert.ok(
        (rust.unsupported_portions || []).some((p) => /Snyk/i.test(p)),
        'Snyk Rust/Cargo gap must remain explicit',
      );
      assert.ok(
        (rust.unsupported_portions || []).some((p) => /DepShield/i.test(p)),
        'DepShield Rust/Cargo gap must remain explicit',
      );
      assert.match(formatted, /Cargo Audit/);
      assert.match(formatted, /Rust\/Cargo/);
    },
  );
});

test('given scanner status needs_setup when mapped then it is skipped, not silently not_started', async () => {
  const { mapScannerStatusToAction } = await import('../src/coverageLedger.js');
  assert.equal(mapScannerStatusToAction('needs_setup'), 'skipped');
});
