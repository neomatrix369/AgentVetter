/**
 * Tests for cli/src/router.js.

 * Author: swami
 * Created: 2026-08-14
 * Scope: preserve prior tiered_router strips when SIE skips; replace on success
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { runRoute } from '../src/router.js';

function makeThenable(value) {
  return {
    then(resolve, reject) {
      return Promise.resolve(value).then(resolve, reject);
    },
  };
}

function findingMatchesEqFilters(finding, filters) {
  if (filters.scanner_source && finding.scanner_source !== filters.scanner_source) return false;
  if (filters.scan_run_id && finding.scan_run_id !== filters.scan_run_id) return false;
  return true;
}

function findingMatchesSelectFilters(finding, filters) {
  if (!findingMatchesEqFilters(finding, filters)) return false;
  if (filters['neq:scanner_source'] && finding.scanner_source === filters['neq:scanner_source']) {
    return false;
  }
  return true;
}

function applyFindingsDelete(findings, filters, calls, deleteError) {
  if (deleteError) return { data: null, error: deleteError };
  calls.deletes.push({ ...filters });
  const before = findings.length;
  for (let i = findings.length - 1; i >= 0; i -= 1) {
    if (!findingMatchesEqFilters(findings[i], filters)) continue;
    findings.splice(i, 1);
  }
  return { data: null, error: null, deleted: before - findings.length };
}

function selectFindingsRows(findings, nonRouterFindings, filters) {
  if (filters['neq:scanner_source'] === 'tiered_router') {
    return nonRouterFindings.filter(
      (f) => !filters.scan_run_id || f.scan_run_id === filters.scan_run_id,
    );
  }
  return findings.filter((f) => findingMatchesSelectFilters(f, filters));
}

function createFindingsQuery({ findings, nonRouterFindings, calls, deleteError }) {
  let filters = {};
  const api = {
    select() { return api; },
    eq(col, val) { filters[col] = val; return api; },
    neq(col, val) { filters[`neq:${col}`] = val; return api; },
    in() { return api; },
    delete() {
      return {
        eq(col, val) {
          filters[col] = val;
          return {
            eq(col2, val2) {
              filters[col2] = val2;
              return makeThenable(applyFindingsDelete(findings, filters, calls, deleteError));
            },
            then: makeThenable({ data: null, error: null }).then.bind(
              makeThenable({ data: null, error: null }),
            ),
          };
        },
      };
    },
    then(resolve, reject) {
      const rows = selectFindingsRows(findings, nonRouterFindings, filters);
      return makeThenable({ data: rows, error: null }).then(resolve, reject);
    },
  };
  return api;
}

function scanRunsOk(batchId, scanRunId, itemId) {
  return {
    data: [{ id: scanRunId, item_id: itemId, batch_id: batchId, status: 'complete' }],
    error: null,
  };
}

function createStubFrom(ctx) {
  const {
    batchId, scanRunId, itemId, item, scanners, nonRouterFindings,
    findings, calls, scannersError, deleteError, insertError,
  } = ctx;

  return function from(table) {
    if (table === 'scan_runs') {
      return {
        select() {
          return {
            eq(col, val) {
              if (col === 'batch_id' && val === batchId) {
                const ok = scanRunsOk(batchId, scanRunId, itemId);
                return {
                  neq() { return makeThenable(ok); },
                  then: makeThenable(ok).then.bind(makeThenable(ok)),
                };
              }
              return makeThenable({ data: [], error: null });
            },
          };
        },
      };
    }
    if (table === 'items') {
      return {
        select() {
          return {
            in() { return makeThenable({ data: [item], error: null }); },
          };
        },
      };
    }
    if (table === 'scan_run_scanners') {
      return {
        select() {
          return {
            eq() {
              return makeThenable({
                data: scannersError ? null : scanners,
                error: scannersError,
              });
            },
          };
        },
      };
    }
    if (table === 'findings') {
      const query = () => createFindingsQuery({
        findings, nonRouterFindings, calls, deleteError,
      });
      return {
        select: () => query(),
        delete: () => query().delete(),
        insert(row) {
          if (insertError) return makeThenable({ data: null, error: insertError });
          calls.inserts.push(row);
          findings.push({ ...row });
          return makeThenable({ data: [row], error: null });
        },
      };
    }
    return {
      select() { return makeThenable({ data: [], error: null }); },
    };
  };
}

/**
 * In-memory Supabase stub for one batch / one scan run.
 * Tracks tiered_router findings so wipe-on-SIE-skip can be asserted.
 */
const ROUTER_STUB_DEFAULTS = {
  batchId: 'batch-1',
  scanRunId: 'run-1',
  itemId: 'item-1',
  item: { id: 'item-1', identifier: 'safe-csv-cleaner', type: 'skill' },
  scanners: [{ scanner_source: 'Snyk', status: 'completed' }],
  nonRouterFindings: [],
  initialRouterFindings: [],
  scannersError: null,
  deleteError: null,
  insertError: null,
};

function createRouterSupabaseStub(options) {
  const {
    batchId,
    scanRunId,
    itemId,
    item,
    scanners,
    nonRouterFindings,
    initialRouterFindings,
    scannersError,
    deleteError,
    insertError,
  } = { ...ROUTER_STUB_DEFAULTS, ...options };

  const findings = [...initialRouterFindings];
  const calls = { deletes: [], inserts: [] };

  return {
    findings,
    calls,
    from: createStubFrom({
      batchId, scanRunId, itemId, item, scanners, nonRouterFindings,
      findings, calls, scannersError, deleteError, insertError,
    }),
  };
}

async function withRouterEnv(fn) {
  const prev = {
    SIE_ENDPOINT: process.env.SIE_ENDPOINT,
    SIE_API_KEY: process.env.SIE_API_KEY,
    ALIBABA_OPENAI_BASE_URL: process.env.ALIBABA_OPENAI_BASE_URL,
    DASHSCOPE_API_KEY: process.env.DASHSCOPE_API_KEY,
    MODEL_STUDIO_MODEL: process.env.MODEL_STUDIO_MODEL,
  };
  process.env.SIE_ENDPOINT = 'https://sie.example';
  process.env.SIE_API_KEY = 'sk-sie-test';
  process.env.ALIBABA_OPENAI_BASE_URL = 'https://ms.example/v1';
  process.env.DASHSCOPE_API_KEY = 'sk-ms-test';
  delete process.env.MODEL_STUDIO_MODEL;
  try {
    return await fn();
  } finally {
    process.env.SIE_ENDPOINT = prev.SIE_ENDPOINT;
    process.env.SIE_API_KEY = prev.SIE_API_KEY;
    process.env.ALIBABA_OPENAI_BASE_URL = prev.ALIBABA_OPENAI_BASE_URL;
    process.env.DASHSCOPE_API_KEY = prev.DASHSCOPE_API_KEY;
    if (prev.MODEL_STUDIO_MODEL === undefined) {
      delete process.env.MODEL_STUDIO_MODEL;
    } else {
      process.env.MODEL_STUDIO_MODEL = prev.MODEL_STUDIO_MODEL;
    }
  }
}

test('given prior routing_review when SIE fails then strip finding is preserved', async () => {
  /**
   * Scenario: Re-route must not wipe Scan → SIE → ■ when SIE is unreachable.
   * Slice: tiered router — preserve strips on SIE skip
   *
   * Given a scan run already has routing_review (SIE-only, not escalated),
   * When runRoute is invoked and SIE throws for that item,
   * Then the prior tiered_router finding remains so the dashboard can show the strip.
   */
  // -- Given --
  const prior = {
    scan_run_id: 'run-1',
    item_id: 'item-1',
    severity: 'green',
    category: 'routing_review',
    scanner_source: 'tiered_router',
    message: JSON.stringify({
      escalated: false,
      signals: { conflicting: false, unusual_status: false, low_confidence: false },
      models: { sie: 'gen-4b', model_studio: null },
      reasoning: { sie: 'clean', model_studio: null },
    }),
  };
  const supabase = createRouterSupabaseStub({ initialRouterFindings: [prior] });

  // -- When --
  await withRouterEnv(() => runRoute('batch-1', {
    getSupabaseFn: () => supabase,
    callSieFn: async () => {
      throw new Error('HTTP 503: provisioning');
    },
  }));

  // -- Then --
  const routerRows = supabase.findings.filter((f) => f.scanner_source === 'tiered_router');
  assert.equal(routerRows.length, 1, 'prior routing_review must survive SIE skip');
  assert.equal(routerRows[0].category, 'routing_review');
  assert.equal(supabase.calls.deletes.length, 0, 'must not delete before a successful route');
  assert.equal(supabase.calls.inserts.length, 0);
});

test('given SIE declines escalate when route succeeds then writes routing_review', async () => {
  /**
   * Scenario: Successful non-escalation persists Scan → SIE → ■ as routing_review.
   * Slice: tiered router — SIE-only path
   *
   * Given scanners completed with no conflict,
   * When SIE returns escalate=false,
   * Then a routing_review finding is written for the scan run.
   */
  // -- Given --
  const supabase = createRouterSupabaseStub();

  // -- When --
  await withRouterEnv(() => runRoute('batch-1', {
    getSupabaseFn: () => supabase,
    callSieFn: async () => ({
      escalate: false,
      low_confidence: false,
      reasoning: 'Scanners agree; no escalation.',
    }),
  }));

  // -- Then --
  assert.equal(supabase.calls.inserts.length, 1);
  assert.equal(supabase.calls.inserts[0].category, 'routing_review');
  const env = JSON.parse(supabase.calls.inserts[0].message);
  assert.equal(env.escalated, false);
  assert.equal(env.models.model_studio, null);
});

test('given SIE escalates with findings when MS succeeds then writes routing_decision', async () => {
  /**
   * Scenario: Conflict escalation reaches Model Studio arbitration.
   * Slice: tiered router — arbitration path
   */
  // -- Given --
  const supabase = createRouterSupabaseStub({
    nonRouterFindings: [
      { scan_run_id: 'run-1', scanner_source: 'Snyk', severity: 'red', category: 'x', message: 'a' },
      { scan_run_id: 'run-1', scanner_source: 'Cisco', severity: 'green', category: 'x', message: 'b' },
    ],
  });

  // -- When --
  await withRouterEnv(() => runRoute('batch-1', {
    getSupabaseFn: () => supabase,
    callSieFn: async () => ({ escalate: true, low_confidence: false, reasoning: 'conflict' }),
    callMsArbitrationFn: async () => ({ final_severity: 'amber', reasoning: 'treat as amber' }),
  }));

  // -- Then --
  assert.equal(supabase.calls.inserts.length, 1);
  assert.equal(supabase.calls.inserts[0].category, 'routing_decision');
  assert.equal(supabase.calls.inserts[0].severity, 'amber');
  const env = JSON.parse(supabase.calls.inserts[0].message);
  assert.equal(env.escalated, true);
  assert.equal(env.models.model_studio, 'qwen3.8-max');
});

test('given SIE escalates with findings when MS fails then writes routing_review fallback', async () => {
  /**
   * Scenario: MS arbitration failure still records a router strip via routing_review.
   * Slice: tiered router — MS failure fallback
   */
  // -- Given --
  const supabase = createRouterSupabaseStub({
    nonRouterFindings: [
      { scan_run_id: 'run-1', scanner_source: 'Snyk', severity: 'red', category: 'x', message: 'a' },
    ],
  });

  // -- When --
  await withRouterEnv(() => runRoute('batch-1', {
    getSupabaseFn: () => supabase,
    callSieFn: async () => ({ escalate: true, low_confidence: true, reasoning: 'uncertain' }),
    callMsArbitrationFn: async () => {
      throw new Error('MS down');
    },
  }));

  // -- Then --
  assert.equal(supabase.calls.inserts[0].category, 'routing_review');
  const env = JSON.parse(supabase.calls.inserts[0].message);
  assert.equal(env.escalated, true);
  assert.match(env.reasoning.model_studio, /Model Studio call failed/);
});

test('given SIE escalates with no findings when MS triage succeeds then writes routing_triage', async () => {
  /**
   * Scenario: Coverage-gap triage when scanners did not all complete.
   * Slice: tiered router — triage path
   */
  // -- Given --
  const supabase = createRouterSupabaseStub({
    scanners: [{ scanner_source: 'Snyk', status: 'unreachable' }],
    nonRouterFindings: [],
  });

  // -- When --
  await withRouterEnv(() => runRoute('batch-1', {
    getSupabaseFn: () => supabase,
    callSieFn: async () => ({ escalate: true, low_confidence: false, reasoning: 'unusual status' }),
    callMsTriageFn: async () => ({
      severity: 'amber',
      recommendation: 're-scan',
      reasoning: 'coverage gap',
    }),
  }));

  // -- Then --
  assert.equal(supabase.calls.inserts[0].category, 'routing_triage');
  assert.equal(supabase.calls.inserts[0].severity, 'amber');
  const env = JSON.parse(supabase.calls.inserts[0].message);
  assert.equal(env.escalated, true);
  assert.match(env.reasoning.model_studio, /re-scan/);
});

test('given SIE escalates with no findings when MS triage fails then writes amber routing_review', async () => {
  /**
   * Scenario: Triage MS failure falls back to amber routing_review.
   * Slice: tiered router — triage MS failure fallback
   */
  // -- Given --
  const supabase = createRouterSupabaseStub({
    scanners: [{ scanner_source: 'Snyk', status: 'unreachable' }],
  });

  // -- When --
  await withRouterEnv(() => runRoute('batch-1', {
    getSupabaseFn: () => supabase,
    callSieFn: async () => ({ escalate: true, low_confidence: false, reasoning: 'gap' }),
    callMsTriageFn: async () => {
      throw new Error('triage timeout');
    },
  }));

  // -- Then --
  assert.equal(supabase.calls.inserts[0].category, 'routing_review');
  assert.equal(supabase.calls.inserts[0].severity, 'amber');
  const env = JSON.parse(supabase.calls.inserts[0].message);
  assert.equal(env.escalated, true);
  assert.match(env.reasoning.model_studio, /triage timeout/);
});

test('given empty findings and all scanners completed when SIE escalates then clamps to routing_review', async () => {
  /**
   * Scenario: §1a — escalate with no findings and unusual_status=false is sanitized off.
   */
  // -- Given --
  const supabase = createRouterSupabaseStub({
    scanners: [{ scanner_source: 'Snyk', status: 'completed' }],
    nonRouterFindings: [],
  });

  // -- When --
  await withRouterEnv(() => runRoute('batch-1', {
    getSupabaseFn: () => supabase,
    callSieFn: async () => ({ escalate: true, low_confidence: true, reasoning: 'should clamp' }),
  }));

  // -- Then --
  assert.equal(supabase.calls.inserts[0].category, 'routing_review');
  const env = JSON.parse(supabase.calls.inserts[0].message);
  assert.equal(env.escalated, false);
  assert.equal(env.signals.low_confidence, false);
});

test('given insert failure after successful SIE when replacing then throws', async () => {
  /**
   * Scenario: Persist failures must surface — silent success would hide missing strips.
   */
  // -- Given --
  const supabase = createRouterSupabaseStub({
    insertError: { message: 'insert denied' },
  });

  // -- When / Then --
  await assert.rejects(
    () => withRouterEnv(() => runRoute('batch-1', {
      getSupabaseFn: () => supabase,
      callSieFn: async () => ({ escalate: false, low_confidence: false, reasoning: 'ok' }),
    })),
    (err) => err && err.message === 'insert denied',
  );
});

test('given live SIE HTTP when chat completes then uses real callSie path', async () => {
  /**
   * Scenario: Default callSie/callChatApi path parses model JSON (no inject).
   */
  // -- Given --
  const supabase = createRouterSupabaseStub();
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => ({
    ok: true,
    async json() {
      return {
        choices: [{
          message: {
            content: '```json\n{"escalate": false, "low_confidence": false, "reasoning": "via fetch"}\n```',
          },
        }],
      };
    },
  });

  // -- When --
  try {
    await withRouterEnv(() => runRoute('batch-1', {
      getSupabaseFn: () => supabase,
    }));
  } finally {
    globalThis.fetch = originalFetch;
  }

  // -- Then --
  assert.equal(supabase.calls.inserts[0].category, 'routing_review');
  const env = JSON.parse(supabase.calls.inserts[0].message);
  assert.equal(env.reasoning.sie, 'via fetch');
});

test('given scanners fetch fails when route runs then item is skipped without wipe', async () => {
  /**
   * Scenario: fetchItemData errors must not delete prior strips.
   * Slice: tiered router — fetch failure soft-skip
   */
  // -- Given --
  const prior = {
    scan_run_id: 'run-1',
    item_id: 'item-1',
    severity: 'green',
    category: 'routing_review',
    scanner_source: 'tiered_router',
    message: '{}',
  };
  const supabase = createRouterSupabaseStub({
    initialRouterFindings: [prior],
    scannersError: { message: 'relation missing' },
  });

  // -- When --
  await withRouterEnv(() => runRoute('batch-1', {
    getSupabaseFn: () => supabase,
    callSieFn: async () => {
      assert.fail('SIE must not be called when fetchItemData fails');
    },
  }));

  // -- Then --
  assert.equal(supabase.findings.filter((f) => f.scanner_source === 'tiered_router').length, 1);
  assert.equal(supabase.calls.deletes.length, 0);
  assert.equal(supabase.calls.inserts.length, 0);
});

test('given MS returns unknown severity when arbitrating then falls back to scanner severity', async () => {
  /**
   * Scenario: pickKnownSeverity rejects non-RAG values.
   * Slice: tiered router — severity sanitization
   */
  // -- Given --
  const supabase = createRouterSupabaseStub({
    nonRouterFindings: [
      { scan_run_id: 'run-1', scanner_source: 'Snyk', severity: 'red', category: 'x', message: 'a' },
    ],
  });

  // -- When --
  await withRouterEnv(() => runRoute('batch-1', {
    getSupabaseFn: () => supabase,
    callSieFn: async () => ({ escalate: true, low_confidence: false, reasoning: 'conflict' }),
    callMsArbitrationFn: async () => ({ final_severity: 'purple', reasoning: 'bad enum' }),
  }));

  // -- Then --
  assert.equal(supabase.calls.inserts[0].category, 'routing_decision');
  assert.equal(supabase.calls.inserts[0].severity, 'red');
});

test('given HTTP non-ok on all SIE attempts when route runs then routing is skipped gracefully', async () => {
  /**
   * Scenario: fetchWithTimeout throws on non-ok, callChatApi retries then throws lastError.
   * Slice: coverage — router.js lines 52-54 (non-ok throw), 87-89 (inner catch), 91 (throw lastError)
   *
   * Given globalThis.fetch returns a non-ok response for every call,
   * When runRoute is invoked with no injected callSieFn (uses real callSie → callChatApi),
   * Then fetchWithTimeout throws on the non-ok body, both retry attempts fail,
   *   lastError is thrown on line 91, and runRoute handles it without crashing.
   */
  // -- Given --
  const supabase = createRouterSupabaseStub({});
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => ({
    ok: false,
    status: 503,
    async text() { return 'Service Unavailable'; },
  });

  // -- When / Then --
  try {
    await withRouterEnv(() => runRoute('batch-1', {
      getSupabaseFn: () => supabase,
      // no callSieFn — exercises real callSie → callChatApi → fetchWithTimeout
    }));
  } finally {
    globalThis.fetch = originalFetch;
  }
  // runRoute swallows SIE failures — if we got here without throwing, lines were reached
  assert.equal(supabase.calls.inserts.length, 0, 'no routing inserted when SIE fails');
});

test('given real callMsArbitration path when SIE escalates then MS arbitration fetch is executed', async () => {
  /**
   * Scenario: callMsArbitration executes via the real HTTP path, not an injected fn.
   * Slice: coverage — router.js lines 124-132 (callMsArbitration body)
   *
   * Given a supabase stub with conflicting scanner findings (to trigger escalation),
   *   and globalThis.fetch mocked to return SIE escalate=true then MS arbitration response,
   * When runRoute is invoked with no callMsArbitrationFn injection,
   * Then the real callMsArbitration body executes and a routing_decision finding is inserted.
   */
  // -- Given --
  const supabase = createRouterSupabaseStub({
    nonRouterFindings: [
      { scan_run_id: 'run-1', scanner_source: 'Snyk', severity: 'red', category: 'vuln', message: 'CVE-x' },
      { scan_run_id: 'run-1', scanner_source: 'Cisco', severity: 'green', category: 'vuln', message: 'clean' },
    ],
    scanners: [
      { scanner_source: 'Snyk', status: 'completed' },
      { scanner_source: 'Cisco', status: 'completed' },
    ],
  });
  const originalFetch = globalThis.fetch;
  let callCount = 0;
  globalThis.fetch = async () => {
    callCount += 1;
    const content = callCount === 1
      ? '{"escalate": true, "low_confidence": false, "reasoning": "conflicting scanners"}'
      : '{"final_severity": "amber", "reasoning": "SIE escalated due to conflict"}';
    return {
      ok: true,
      async json() {
        return { choices: [{ message: { content } }] };
      },
    };
  };

  // -- When --
  try {
    await withRouterEnv(() => runRoute('batch-1', {
      getSupabaseFn: () => supabase,
      callSieFn: undefined,           // use real callSie
      callMsArbitrationFn: undefined, // use real callMsArbitration
    }));
  } finally {
    globalThis.fetch = originalFetch;
  }

  // -- Then --
  assert.ok(callCount >= 2, 'both SIE and MS arbitration fetch calls were made');
  const decision = supabase.calls.inserts.find((f) => f.category === 'routing_decision');
  assert.ok(decision, 'routing_decision finding inserted via real MS arbitration path');
});

test('given real callMsTriage path when SIE escalates empty findings then MS triage fetch is executed', async () => {
  /**
   * Scenario: callMsTriage executes via the real HTTP path, not an injected fn.
   * Slice: coverage — router.js lines 134-142 (callMsTriage body)
   *
   * Given a supabase stub with no non-router findings but a failed scanner (unusual_status=true),
   *   and globalThis.fetch mocked to return SIE escalate=true then MS triage response,
   * When runRoute is invoked with no callMsTriageFn injection,
   * Then the real callMsTriage body executes and a routing_triage finding is inserted.
   */
  // -- Given --
  const supabase = createRouterSupabaseStub({
    nonRouterFindings: [],
    scanners: [
      { scanner_source: 'Snyk', status: 'partial-failed' },
    ],
  });
  const originalFetch = globalThis.fetch;
  let callCount = 0;
  globalThis.fetch = async () => {
    callCount += 1;
    const content = callCount === 1
      ? '{"escalate": true, "low_confidence": false, "reasoning": "scanner failed to complete"}'
      : '{"severity": "amber", "recommendation": "re-scan with valid credentials", "reasoning": "coverage gap"}';
    return {
      ok: true,
      async json() {
        return { choices: [{ message: { content } }] };
      },
    };
  };

  // -- When --
  try {
    await withRouterEnv(() => runRoute('batch-1', {
      getSupabaseFn: () => supabase,
      callSieFn: undefined,       // use real callSie
      callMsTriageFn: undefined,  // use real callMsTriage
    }));
  } finally {
    globalThis.fetch = originalFetch;
  }

  // -- Then --
  assert.ok(callCount >= 2, 'both SIE and MS triage fetch calls were made');
  const triage = supabase.calls.inserts.find((f) => f.category === 'routing_triage');
  assert.ok(triage, 'routing_triage finding inserted via real MS triage path');
});

test('given replace delete fails when writing routing_review then error propagates', async () => {
  /**
   * Scenario: DB delete failure during replace must surface.
   * Slice: tiered router — replaceRouterFinding error path
   */
  // -- Given --
  const supabase = createRouterSupabaseStub({
    deleteError: { message: 'delete denied' },
  });

  // -- When / Then --
  await assert.rejects(
    () => withRouterEnv(() => runRoute('batch-1', {
      getSupabaseFn: () => supabase,
      callSieFn: async () => ({
        escalate: false,
        low_confidence: false,
        reasoning: 'clean',
      }),
    })),
    (err) => {
      assert.equal(err && err.message, 'delete denied');
      return true;
    },
  );
  assert.equal(supabase.calls.inserts.length, 0);
});

test('given model reasoning quotes a secret when routing persists then the stored message is masked', async () => {
  /**
   * Scenario: a secret quoted in SIE reasoning is not stored in the anon-readable findings table.
   * Slice: stored-evidence masking (PR #212 review follow-up).
   *
   * Given SIE reasoning contains an API key-looking value,
   * When routing writes the routing_review finding,
   * Then the stored message omits the value and still parses as JSON.
   */
  // -- Given --
  const fakeKey = 'sk-' + 'live-4f2b9abcdef';
  const supabase = createRouterSupabaseStub();

  // -- When --
  await withRouterEnv(() => runRoute('batch-1', {
    getSupabaseFn: () => supabase,
    callSieFn: async () => ({
      escalate: false,
      low_confidence: false,
      reasoning: `The scanned file hardcodes ${fakeKey} in config.`,
    }),
  }));

  // -- Then --
  const stored = supabase.calls.inserts[0].message;
  assert.ok(!stored.includes(fakeKey), 'secret must not be stored');
  assert.ok(stored.includes('[REDACTED_KEY]'));
  assert.ok(JSON.parse(stored).reasoning, 'envelope still carries its reasoning');
});

