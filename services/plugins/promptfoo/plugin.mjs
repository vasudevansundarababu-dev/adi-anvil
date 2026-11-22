// Promptfoo verifier plug-in: adi.verifier-job.v1 on stdin -> adi.verifier-result.v1 on stdout.
// Each block runs one Promptfoo model-graded assertion (llm-rubric, model-graded-closedqa or factuality) on the text
// at `settings.target` (an evidence path). The judge never runs in this sandbox (no network): it answers with
// `job.judge_answers[block_id]` when the RL Gym supplies one (recorded answers for known cases, or an approved judge
// model's answer obtained through the RL Gym's gateway), otherwise with the local mock judge (deterministic).
import promptfoo from 'promptfoo';

const MISSING = Symbol('missing');

function tokens(path) {
  const out = [];
  for (const part of path.split('.')) {
    const m = part.match(/^([^[]*)((\[[^\]]*\])*)$/);
    if (m[1]) out.push(m[1]);
    for (const idx of m[2].matchAll(/\[([^\]]*)\]/g)) out.push(idx[1] === '*' ? '*' : Number(idx[1]));
  }
  return out;
}

function resolve(root, path) {
  let values = [root];
  let many = false;
  for (const t of tokens(path)) {
    const next = [];
    for (const v of values) {
      if (t === '*') {
        if (!Array.isArray(v)) return MISSING;
        next.push(...v);
        many = true;
      } else if (typeof t === 'number') {
        if (!Array.isArray(v) || t >= v.length) { if (many) continue; return MISSING; }
        next.push(v[t]);
      } else {
        if (v === null || typeof v !== 'object' || !(t in v)) { if (many) continue; return MISSING; }
        next.push(v[t]);
      }
    }
    values = next;
  }
  return many ? values : values[0];
}

function mockJudge(rubric, text) {
  // Deterministic stand-in: passes when the text is a real sentence and shares a content word with the rubric.
  const words = (s) => new Set(String(s).toLowerCase().match(/[a-z]{5,}/g) || []);
  const shared = [...words(rubric)].filter((w) => words(text).has(w));
  const pass = String(text).trim().length >= 12 && shared.length > 0;
  return { pass, score: pass ? 1 : 0, reason: pass ? `mock judge: mentions ${shared.slice(0, 3).join(', ')}` : 'mock judge: does not address the rubric' };
}

function line(block, verdict, expected, actual, detail, points = null) {
  return { block_id: block.id, verdict, points, expected, actual, on_fail: verdict === 'fail' ? block.on_fail ?? null : null, detail };
}

async function runBlock(job, root, block) {
  const s = block.settings || {};
  const text = resolve(root, s.target || 'output');
  if (text === MISSING || text === null || text === undefined || text === '') {
    return line(block, 'blocked', s.rubric, { missing: s.target }, `evidence ${s.target} is missing`);
  }
  const value = typeof text === 'string' ? text : JSON.stringify(text);
  const given = (job.judge_answers || {})[block.id];
  const answer = given ?? mockJudge(s.rubric, value);
  const judgeName = given ? (given.judge || 'recorded') : 'mock';
  const judge = { id: () => `rlgym-judge-${judgeName}`, callApi: async () => ({ output: JSON.stringify({ pass: !!answer.pass, score: Number(answer.score ?? (answer.pass ? 1 : 0)), reason: String(answer.reason || '') }) }) };
  const target = { id: () => 'rlgym-evidence', callApi: async () => ({ output: value }) };
  const assertion = { type: s.assertion || 'llm-rubric', value: s.rubric, provider: judge, threshold: s.threshold ?? 0.5 };
  if (assertion.type === 'factuality' || assertion.type === 'model-graded-closedqa') assertion.value = s.rubric;
  const r = await promptfoo.evaluate(
    { prompts: ['{{x}}'], providers: [target], tests: [{ vars: { x: '1' }, assert: [assertion] }] },
    { cache: false, writeLatestResults: false, maxConcurrency: 1, showProgressBar: false },
  );
  const res = (await r.toEvaluateSummary()).results[0];
  const comp = res.gradingResult?.componentResults?.[0] || res.gradingResult || {};
  return line(block, res.success ? 'pass' : 'fail', s.rubric, { score: comp.score ?? res.score, reason: comp.reason, judge: judgeName }, `promptfoo ${assertion.type}, judge ${judgeName}`, comp.score ?? res.score);
}

async function main() {
  let raw = '';
  for await (const chunk of process.stdin) raw += chunk;
  let job;
  try {
    job = JSON.parse(raw);
    if (job.schema !== 'adi.verifier-job.v1' || !Array.isArray(job.blocks)) throw new Error('schema');
  } catch (e) {
    process.stderr.write(`bad job: ${e.message}`);
    process.exit(2);
  }
  const root = { ...(job.evidence || {}), case_reference: job.case_reference, slots: job.slots };
  const results = [];
  for (const block of job.blocks) {
    try {
      results.push(await runBlock(job, root, block));
    } catch (e) {
      results.push(line(block, 'blocked', null, { error: e.name }, String(e.message).slice(0, 300)));
    }
  }
  // Promptfoo logs to stdout; the result is the last line, and the runner reads only that.
  process.stdout.write('\n' + JSON.stringify({ schema: 'adi.verifier-result.v1', results, plugin: { id: 'promptfoo', version: '1.0.0' } }) + '\n');
}

await main();
