import { getSupabase } from './supabaseClient.js';
import { maskSecrets } from './evidenceVerify.js';

const SIE_TIMEOUT_MS = 15000;
const MS_TIMEOUT_MS = 30000;

function resolveModel(cliArg, envKey, defaultValue) {
  if (cliArg) return cliArg;
  const envValue = (process.env[envKey] || '').trim();
  if (envValue) return envValue;
  return defaultValue;
}

function computeConflicting(findings) {
  const valid = findings.filter(f => ['red', 'amber', 'green'].includes(f.severity));
  const bySrc = {};
  for (const f of valid) {
    if (!bySrc[f.scanner_source]) bySrc[f.scanner_source] = new Set();
    bySrc[f.scanner_source].add(f.severity);
  }
  // Each source must agree with itself; cross-source disagreement is the signal
  const srcSeverities = Object.values(bySrc)
    .filter(s => s.size === 1)
    .map(s => [...s][0]);
  return srcSeverities.length >= 2 && new Set(srcSeverities).size >= 2;
}

function computeSeverityNonEscalated(findings) {
  // §3a: zero findings → green; else worst-case among non-router findings
  const RANK = { red: 2, amber: 1, green: 0 };
  const valid = findings.filter(f => ['red', 'amber', 'green'].includes(f.severity));
  if (valid.length === 0) return 'green';
  return valid.reduce((best, f) => (RANK[f.severity] > RANK[best] ? f.severity : best), 'green');
}

function buildEnvelope(escalated, signals, models, reasoning) {
  return { escalated, signals, models, reasoning };
}

function extractJson(text) {
  const stripped = text.replace(/```(?:json)?\n?([\s\S]*?)\n?```/g, '$1').trim();
  const start = stripped.indexOf('{');
  const end = stripped.lastIndexOf('}');
  if (start === -1 || end === -1) throw new Error(`No JSON object in: ${stripped.slice(0, 200)}`);
  return JSON.parse(stripped.slice(start, end + 1));
}

async function fetchWithTimeout(url, init, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { ...init, signal: controller.signal });
    if (!response.ok) {
      const body = await response.text();
      throw new Error(`HTTP ${response.status}: ${body.slice(0, 200)}`);
    }
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

async function callChatApi(baseUrl, apiKey, model, systemPrompt, userContent, timeoutMs) {
  const url = `${baseUrl.replace(/\/$/, '')}/chat/completions`;
  const init = {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      model,
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: userContent },
      ],
    }),
  };

  let lastError;
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const payload = await fetchWithTimeout(url, init, timeoutMs);
      const content = payload?.choices?.[0]?.message?.content;
      if (!content) throw new Error('Empty content in response');
      return extractJson(content);
    } catch (err) {
      lastError = err;
      if (attempt === 0) await new Promise(r => setTimeout(r, 500));
    }
  }
  throw lastError;
}

const SIE_SYSTEM = `You review scanner findings for one item and decide whether it needs deeper review by a stronger model.
Input: item name, a list of {scanner_source, severity, category, message} from findings (this list may be empty), each scanner's completion status for this item (completed / skipped_missing_credential / unreachable / partial-failed / not_applicable), and two facts that are already known with certainty — conflicting=<true|false> (scanners disagree on severity for this item) and unusual_status=<true|false> (a scanner failed to complete normally). Do not re-derive or second-guess these two facts.
Task: Judge low_confidence — is the finding text vague, generic, or does the severity seem unjustified by the description? (There is no upstream confidence score — judge this from the text itself.) If the findings list is empty, this is always false — there is no text to judge.
Then decide overall whether escalation is warranted, weighing all three signals together (conflicting and unusual_status as given, plus your own low_confidence judgment) — any one firing can be enough, but conflicting or multiple signals together should weigh more than low_confidence alone. If the findings list is empty, base your decision on unusual_status alone.
Output JSON only: {"escalate": true|false, "low_confidence": bool, "reasoning": "<1-2 sentences>"}`;

const MS_ARBITRATION_SYSTEM = `You arbitrate a disputed or uncertain security finding for an AI skill/MCP server.
Input: item name, the {scanner_source, severity, category, message} entries, the routing signals (conflicting, unusual_status — known facts; low_confidence — SIE's judgment), and SIE's reasoning for why this needed escalation.
Task: Decide the most defensible final severity (red/amber/green) and explain why, referencing which scanner's read is more credible, what made this uncertain, and why.
Output JSON only: {"final_severity": "red"|"amber"|"green", "reasoning": "<2-3 sentences>"}`;

const MS_TRIAGE_SYSTEM = `You assess an AI skill/MCP server item that could not be fully scanned — no scanner findings exist, and at least one scanner failed to complete normally, so there is nothing to point to as a specific vulnerability.
Input: item name, item type (skill or mcp_server), which scanners were expected and each one's completion status (completed / skipped_missing_credential / unreachable / partial-failed / not_applicable), and SIE's reasoning for flagging this coverage gap.
Task: Do not invent or guess at specific vulnerabilities — there is no finding content to evaluate. Instead, assess how concerning the coverage gap itself is and recommend what should happen next.
Output JSON only: {"severity": "red"|"amber"|"green", "recommendation": "<short action>", "reasoning": "<2-3 sentences>"}`;

function sieUserContent(itemLabel, findings, scanners, conflicting, unusual_status) {
  return JSON.stringify({
    item: itemLabel,
    findings: findings.map(f => ({ scanner_source: f.scanner_source, severity: f.severity, category: f.category, message: f.message })),
    scanner_statuses: scanners.map(s => ({ scanner: s.scanner_source, status: s.status })),
    conflicting,
    unusual_status,
  });
}

async function callSie(itemLabel, findings, scanners, conflicting, unusual_status, model, endpoint, apiKey) {
  return callChatApi(`${endpoint.replace(/\/$/, '')}/v1`, apiKey, model, SIE_SYSTEM, sieUserContent(itemLabel, findings, scanners, conflicting, unusual_status), SIE_TIMEOUT_MS);
}

async function callMsArbitration(itemLabel, findings, signals, sieReasoning, model, baseUrl, apiKey) {
  const user = JSON.stringify({
    item: itemLabel,
    findings: findings.map(f => ({ scanner_source: f.scanner_source, severity: f.severity, category: f.category, message: f.message })),
    signals,
    sie_reasoning: sieReasoning,
  });
  return callChatApi(baseUrl, apiKey, model, MS_ARBITRATION_SYSTEM, user, MS_TIMEOUT_MS);
}

async function callMsTriage(itemLabel, itemType, scanners, sieReasoning, model, baseUrl, apiKey) {
  const user = JSON.stringify({
    item: itemLabel,
    item_type: itemType || 'unknown',
    scanner_statuses: scanners.map(s => ({ scanner: s.scanner_source, status: s.status })),
    sie_reasoning: sieReasoning,
  });
  return callChatApi(baseUrl, apiKey, model, MS_TRIAGE_SYSTEM, user, MS_TIMEOUT_MS);
}

async function fetchItemData(supabase, scanRun) {
  const { data: scanners, error: scannersError } = await supabase
    .from('scan_run_scanners')
    .select('*')
    .eq('scan_run_id', scanRun.id);
  if (scannersError) throw scannersError;

  const { data: allFindings, error: findingsError } = await supabase
    .from('findings')
    .select('*')
    .eq('scan_run_id', scanRun.id)
    .neq('scanner_source', 'tiered_router');
  if (findingsError) throw findingsError;

  const findings = allFindings || [];
  const scannersList = scanners || [];

  return {
    findings,
    scanners: scannersList,
    conflicting: computeConflicting(findings),
    unusual_status: scannersList.some(s => s.status !== 'completed'),
  };
}

/**
 * Replace tiered_router rows for one scan run only after a successful route
 * decision. Do not batch-delete first: if SIE skips an item, prior
 * routing_review / decision rows must remain so the dashboard keeps
 * "Scan → SIE → ■" (or Model Studio) strips.
 */
async function replaceRouterFinding(supabase, scanRun, severity, category, envelope) {
  const { error: deleteError } = await supabase
    .from('findings')
    .delete()
    .eq('scanner_source', 'tiered_router')
    .eq('scan_run_id', scanRun.id);
  if (deleteError) {
    console.error(`[critical] Delete failed for scan_run ${scanRun.id}: ${deleteError.message}`);
    throw deleteError;
  }

  const { error } = await supabase.from('findings').insert({
    scan_run_id: scanRun.id,
    item_id: scanRun.item_id,
    severity,
    category,
    scanner_source: 'tiered_router',
    // Model reasoning can quote secrets from scanned code; mask before the anon-readable table.
    message: maskSecrets(JSON.stringify(envelope)).text,
  });
  if (error) {
    console.error(`[critical] Insert failed for scan_run ${scanRun.id}: ${error.message}`);
    throw error;
  }
}

function resolveRouteConfig(opts = {}) {
  const sieModel = resolveModel(opts.sieModel, 'SIE_MODEL', 'gen-4b');
  const msModel = resolveModel(opts.modelStudioModel, 'MODEL_STUDIO_MODEL', 'qwen3.8-max');
  const sieEndpoint = (process.env.SIE_ENDPOINT || 'https://api.superlinked.com').trim();
  const sieApiKey = (process.env.SIE_API_KEY || '').trim();
  const msBaseUrl = (process.env.ALIBABA_OPENAI_BASE_URL || '').trim();
  const msApiKey = (process.env.DASHSCOPE_API_KEY || '').trim();

  if (!sieEndpoint || !sieApiKey) throw new Error('SIE_ENDPOINT and SIE_API_KEY must be set');
  if (!msBaseUrl || !msApiKey) throw new Error('ALIBABA_OPENAI_BASE_URL and DASHSCOPE_API_KEY must be set');

  return { sieModel, msModel, sieEndpoint, sieApiKey, msBaseUrl, msApiKey };
}

async function loadBatchRuns(supabase, batchId) {
  const { data: scanRuns, error: scanRunsError } = await supabase
    .from('scan_runs')
    .select('*')
    .eq('batch_id', batchId)
    .neq('status', 'failed');
  if (scanRunsError) throw scanRunsError;

  const runs = scanRuns || [];
  const itemIds = [...new Set(runs.map(sr => sr.item_id))];
  const { data: itemsData, error: itemsError } = await supabase
    .from('items')
    .select('*')
    .in('id', itemIds);
  if (itemsError) throw itemsError;

  const itemsById = Object.fromEntries((itemsData || []).map(item => [item.id, item]));
  return { runs, itemsById };
}

function sanitizeEscalationDecision(sieResult, hasFindings, conflicting, unusual_status) {
  // §1a defensive sanitization on empty findings
  const sanitizedLowConf = hasFindings ? Boolean(sieResult.low_confidence) : false;
  const sanitizedConflicting = hasFindings ? conflicting : false;

  // §1a: empty + unusual_status=false + SIE says escalate → clamp to false
  let escalate = Boolean(sieResult.escalate);
  if (!hasFindings && !unusual_status && escalate) escalate = false;

  return {
    escalate,
    signals: { conflicting: sanitizedConflicting, unusual_status, low_confidence: sanitizedLowConf },
    sieReasoning: sieResult.reasoning || '',
  };
}

function pickKnownSeverity(value, fallback) {
  if (['red', 'amber', 'green'].includes(value)) return value;
  return fallback;
}

async function writeNonEscalatedFinding(supabase, scanRun, itemLabel, findings, signals, sieModel, sieReasoning) {
  const severity = computeSeverityNonEscalated(findings);
  const envelope = buildEnvelope(false, signals, { sie: sieModel, model_studio: null }, { sie: sieReasoning, model_studio: null });
  await replaceRouterFinding(supabase, scanRun, severity, 'routing_review', envelope);
  console.log(`[route] ${itemLabel}: routing_review severity=${severity}`);
}

async function writeArbitrationFinding(supabase, scanRun, itemLabel, findings, signals, models, sieReasoning, msResult, msFailure) {
  if (msResult) {
    const severity = pickKnownSeverity(msResult.final_severity, computeSeverityNonEscalated(findings));
    const envelope = buildEnvelope(true, signals, models, { sie: sieReasoning, model_studio: msResult.reasoning || '' });
    await replaceRouterFinding(supabase, scanRun, severity, 'routing_decision', envelope);
    console.log(`[route] ${itemLabel}: routing_decision severity=${severity}`);
    return;
  }

  // §1a MS failure fallback → routing_review
  const severity = computeSeverityNonEscalated(findings);
  const envelope = buildEnvelope(true, signals, { sie: models.sie, model_studio: null }, { sie: sieReasoning, model_studio: msFailure });
  await replaceRouterFinding(supabase, scanRun, severity, 'routing_review', envelope);
  console.log(`[route] ${itemLabel}: routing_review (ms-fallback) severity=${severity}`);
}

async function runArbitrationPath(supabase, scanRun, itemLabel, findings, signals, sieReasoning, config, deps) {
  const { sieModel, msModel, msBaseUrl, msApiKey } = config;
  let msResult;
  let msFailure;
  try {
    msResult = await deps.callMsArbitration(
      itemLabel, findings, signals, sieReasoning, msModel, msBaseUrl, msApiKey,
    );
    console.log(`[ms] ${itemLabel}: arbitration severity=${msResult.final_severity}`);
  } catch (err) {
    msFailure = `Model Studio call failed: ${err.message.slice(0, 120)}; manual review recommended.`;
    console.warn(`[warn] MS arbitration failed for ${itemLabel}: ${err.message}`);
  }

  await writeArbitrationFinding(
    supabase, scanRun, itemLabel, findings, signals,
    { sie: sieModel, model_studio: msModel }, sieReasoning, msResult, msFailure,
  );
}

async function writeTriageFinding(supabase, scanRun, itemLabel, signals, models, sieReasoning, msResult, msFailure) {
  if (msResult) {
    const severity = pickKnownSeverity(msResult.severity, 'amber');
    const triageNote = [msResult.recommendation, msResult.reasoning].filter(Boolean).join('. ');
    const envelope = buildEnvelope(true, signals, models, { sie: sieReasoning, model_studio: triageNote });
    await replaceRouterFinding(supabase, scanRun, severity, 'routing_triage', envelope);
    console.log(`[route] ${itemLabel}: routing_triage severity=${severity}`);
    return;
  }

  // §1a MS failure fallback → routing_review, amber for zero-findings coverage gap
  const envelope = buildEnvelope(true, signals, { sie: models.sie, model_studio: null }, { sie: sieReasoning, model_studio: msFailure });
  await replaceRouterFinding(supabase, scanRun, 'amber', 'routing_review', envelope);
  console.log(`[route] ${itemLabel}: routing_review (triage-ms-fallback) severity=amber`);
}

async function runTriagePath(supabase, scanRun, itemLabel, itemType, scanners, signals, sieReasoning, config, deps) {
  const { sieModel, msModel, msBaseUrl, msApiKey } = config;
  let msResult;
  let msFailure;
  try {
    msResult = await deps.callMsTriage(
      itemLabel, itemType, scanners, sieReasoning, msModel, msBaseUrl, msApiKey,
    );
    console.log(`[ms] ${itemLabel}: triage severity=${msResult.severity}`);
  } catch (err) {
    msFailure = `Model Studio call failed: ${err.message.slice(0, 120)}; manual review recommended.`;
    console.warn(`[warn] MS triage failed for ${itemLabel}: ${err.message}`);
  }

  await writeTriageFinding(
    supabase, scanRun, itemLabel, signals,
    { sie: sieModel, model_studio: msModel }, sieReasoning, msResult, msFailure,
  );
}

async function routeOneItem(supabase, scanRun, item, config, deps) {
  const itemLabel = item?.identifier || scanRun.item_id;
  const itemType = item?.type || null;
  const { sieModel, sieEndpoint, sieApiKey } = config;

  let itemData;
  try {
    itemData = await fetchItemData(supabase, scanRun);
  } catch (err) {
    console.error(`[error] fetchItemData failed for ${itemLabel}: ${err.message}`);
    return;
  }

  const { findings, scanners, conflicting, unusual_status } = itemData;
  const hasFindings = findings.length > 0;
  console.log(`[route] ${itemLabel}: findings=${findings.length}, conflicting=${conflicting}, unusual_status=${unusual_status}`);

  let sieResult;
  try {
    sieResult = await deps.callSie(
      itemLabel, findings, scanners, conflicting, unusual_status, sieModel, sieEndpoint, sieApiKey,
    );
    console.log(`[sie] ${itemLabel}: escalate=${sieResult.escalate}, low_confidence=${sieResult.low_confidence}`);
  } catch (err) {
    console.warn(`[warn] SIE failed for ${itemLabel}: ${err.message} — skipping`);
    return;
  }

  const { escalate, signals, sieReasoning } = sanitizeEscalationDecision(
    sieResult, hasFindings, conflicting, unusual_status,
  );

  if (!escalate) {
    await writeNonEscalatedFinding(supabase, scanRun, itemLabel, findings, signals, sieModel, sieReasoning);
    return;
  }
  if (hasFindings) {
    await runArbitrationPath(supabase, scanRun, itemLabel, findings, signals, sieReasoning, config, deps);
    return;
  }
  await runTriagePath(supabase, scanRun, itemLabel, itemType, scanners, signals, sieReasoning, config, deps);
}

export async function runRoute(batchId, opts = {}) {
  const config = resolveRouteConfig(opts);
  console.log(`SIE model: ${config.sieModel}, Model Studio model: ${config.msModel}`);

  const deps = {
    callSie: opts.callSieFn || callSie,
    callMsArbitration: opts.callMsArbitrationFn || callMsArbitration,
    callMsTriage: opts.callMsTriageFn || callMsTriage,
  };
  const supabase = (opts.getSupabaseFn || getSupabase)();

  // Intentionally no batch-wide delete: prior strips survive SIE/MS skips.
  const { runs, itemsById } = await loadBatchRuns(supabase, batchId);
  console.log(`[route] Batch ${batchId}: ${runs.length} items`);

  for (const scanRun of runs) {
    await routeOneItem(supabase, scanRun, itemsById[scanRun.item_id], config, deps);
  }
}
