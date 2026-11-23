/**
 * Judge command inputs/outputs: quorum rule on the final verdict, candidate
 * loading from a batch, and persistence of panel runs and judgements.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { coerceFinal, loadJudgeCandidates, persistPanelRun } from '../src/judgePanel.js';

const answered = (slot) => ({ slot, model: `m${slot}`, status: 'answered', verdict: 'true_positive', confidence: 0.9 });

test('given only the final judge answered when coerceFinal then verdict is needs_review, not true_positive', () => {
  // -- Given --
  const finalJudge = { status: 'answered', verdict: 'true_positive', confidence: 0.99 };
  const judgements = [{ slot: 1, status: 'error' }, { slot: 2, status: 'timeout' }, { slot: 3, status: 'error' }];

  // -- When --
  const result = coerceFinal(finalJudge, judgements);

  // -- Then --
  assert.equal(result.verdict, 'needs_review');
});

test('given two answered panel judges when coerceFinal then the final verdict stands', () => {
  // -- Given --
  const finalJudge = { status: 'answered', verdict: 'true_positive', confidence: 0.95 };
  const judgements = [answered(1), answered(2), { slot: 3, status: 'error' }];

  // -- When / Then --
  assert.equal(coerceFinal(finalJudge, judgements).verdict, 'true_positive');
});

function fakeJudgeSupabase({ runs, findings, items }) {
  const inserted = { panel_runs: [], judgements: [] };
  return {
    inserted,
    from(table) {
      const rowsFor = { scan_runs: runs, findings, items };
      const result = { data: rowsFor[table] || [], error: null };
      const chain = {
        select() { return chain; },
        eq() { return chain; },
        neq() { return chain; },
        in() { return Promise.resolve(result); },
        then: (resolve) => resolve(result),
        insert(rows) {
          if (table === 'judge_panel_runs') inserted.panel_runs.push(rows);
          if (table === 'judge_panel_judgements') inserted.judgements.push(...rows);
          return {
            select() { return { single: async () => ({ data: { id: 'panel-1' }, error: null }) }; },
            then: (resolve) => resolve({ error: null }),
          };
        },
      };
      return chain;
    },
  };
}

test('given a batch with findings when loadJudgeCandidates then one candidate per finding with item label', async () => {
  // -- Given --
  const supabase = fakeJudgeSupabase({
    runs: [{ id: 'run-1' }],
    findings: [{ id: 'f-1', scan_run_id: 'run-1', item_id: 'item-1', category: 'exfil', severity: 'red', snippet: 'curl x', message: 'm' }],
    items: [{ id: 'item-1', identifier: 'skills/x', name: 'x' }],
  });

  // -- When --
  const candidates = await loadJudgeCandidates(supabase, 'batch-1');

  // -- Then --
  assert.equal(candidates.length, 1);
  assert.equal(candidates[0].finding_id, 'f-1');
  assert.equal(candidates[0].item_label, 'skills/x');
  assert.equal(candidates[0].finding.severity, 'red');
  assert.equal(candidates[0].evidence.snippet, 'curl x');
});

test('given a panel run with judgements when persistPanelRun then run and judgements are inserted without non-column fields', async () => {
  // -- Given --
  const supabase = fakeJudgeSupabase({});
  const panelRun = {
    scan_run_id: 'run-1', item_id: 'item-1', finding_id: 'f-1',
    answered_count: 1, total_judges: 1, disagreement: false,
    final_verdict: 'needs_review', final_confidence: 0.5, final_reason: 'r', final_model: 'm',
    final_raw_response: '{}', prompt_version: 'v1', sie_run_id: null, inventory_note: null,
    judgements: [{ slot: 1, model: 'm1', status: 'answered', verdict: 'true_positive', confidence: 0.9 }],
    final_judge: { status: 'answered' }, created_at: '2026-01-01T00:00:00Z',
  };

  // -- When --
  await persistPanelRun(supabase, panelRun);

  // -- Then --
  assert.equal(supabase.inserted.panel_runs.length, 1);
  assert.equal(supabase.inserted.panel_runs[0].final_judge, undefined);
  assert.equal(supabase.inserted.panel_runs[0].judgements, undefined);
  assert.equal(supabase.inserted.judgements[0].panel_run_id, 'panel-1');
  assert.equal(supabase.inserted.judgements[0].slot, 1);
});
