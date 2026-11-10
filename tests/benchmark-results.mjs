// Presentation/API contract fixtures only. These are not persisted benchmark
// records, qualification receipts, human approvals or native execution evidence.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const requireWeb = createRequire(path.resolve('apps/web/package.json'));
const ts = requireWeb('typescript');
const React = requireWeb('react');
const { renderToStaticMarkup } = requireWeb('react-dom/server');
function compile(file, imports) {
  const code = ts.transpileModule(readFileSync(file, 'utf8'), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      jsx: ts.JsxEmit.ReactJSX,
    },
  }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(
    code,
    {
      module,
      exports: module.exports,
      Error,
      require: (id) => (id in imports ? imports[id] : requireWeb(id)),
    },
    { filename: file },
  );
  return module.exports;
}
const protocolHash = 'a'.repeat(64);
const comparison = () => ({
  run_id: 'contract-run',
  protocol_revision_id: 'contract-protocol',
  subject_sha256: protocolHash,
  state: 'awaiting_review',
  origin: 'original_synthetic_fixture',
  planned_cells: 18,
  checkpoint_event_seq: 8,
  blockers: [],
  model_slots: [
    {
      slot: 0,
      provider: 'contract-provider',
      model_id: 'exact-contract-model',
    },
  ],
  task_labels: { task: 'Fictional task' },
  cells: [
    {
      cell_id: 'cell',
      task_revision_id: 'task',
      slot: 0,
      repetition: 0,
      state: 'completed',
      validity: 'valid',
      reconciled: false,
    },
  ],
});
const stored = () => ({
  score_revision_id: 'stored-score-revision',
  revision: 7,
  projection_sha256: 'b'.repeat(64),
  review_state: 'pending_first_review',
  reviews: 0,
  projection: {
    profile: 'sme-scorecard-v1',
    protocol_sha256: protocolHash,
    origin: 'original_synthetic_fixture',
    complete: false,
    execution_complete: false,
    models: [
      {
        slot: 0,
        provider: 'contract-provider',
        model_id: 'exact-contract-model',
        planned: 6,
        scored: 3,
        completion: 'incomplete',
        score_complete: false,
        primary: null,
        diagnostic: {
          earned_points: '40.5',
          possible_points: '81',
          included: [],
          excluded: [],
          complete_repetitions: [
            {
              repetition: 0,
              earned_points: '40.5',
              possible_points: '81',
              percent: '50.00',
            },
          ],
          complete_repetition_mean: {
            earned_points: '40.5',
            possible_points: '81',
            percent: '50.00',
          },
        },
        duration: { median_ms: 1500, samples: 3 },
        cost: {
          candidate_micro_usd: null,
          judge_micro_usd: null,
          combined_micro_usd: null,
          status: 'unknown',
        },
      },
    ],
  },
});
function helpers(get) {
  return compile('apps/web/src/lib/benchmark-results.ts', {
    './benchmark': {
      benchmarkGet: get,
      benchmarkPath: (base) => base + '/workspace/benchmarks',
    },
  });
}
const utilities = helpers(() => {
  throw new Error('Unexpected API request');
});
const { BenchmarkResultDashboard } = compile('apps/web/src/components/BenchmarkResults.tsx', {
  '../lib/benchmark-results': utilities,
  './BenchmarkCellEvidence': {
    default: () => React.createElement('span', null, 'Evidence remains explicitly requested'),
  },
  './BenchmarkResults.module.css': {
    default: new Proxy({}, { get: (_, name) => String(name) }),
  },
});
const { QualificationEvidenceReport } = compile(
  'apps/web/src/components/BenchmarkQualificationEvidence.tsx',
  {
    '../lib/benchmark': {
      benchmarkGet() {
        throw new Error('Unexpected API request');
      },
    },
    './BenchmarkResults.module.css': {
      default: new Proxy({}, { get: (_, name) => String(name) }),
    },
  },
);
const render = (score = stored(), extra = {}) =>
  renderToStaticMarkup(
    React.createElement(BenchmarkResultDashboard, {
      comparison: comparison(),
      score,
      base: '/projects/project',
      busy: false,
      loaded: true,
      error: '',
      refresh() {},
      ...extra,
    }),
  );

test('loads real comparison and immutable result GET paths, not embedded preview scores', async () => {
  const calls = [];
  const api = helpers(async (base, suffix) => {
    calls.push([base, suffix]);
    return suffix.endsWith('/results') ? stored() : comparison();
  });
  const result = await api.loadBenchmarkResults('/projects/project', 'contract-run');
  assert.equal(result.score.revision, 7);
  assert.deepEqual(calls, [
    ['/projects/project', '/comparisons/contract-run'],
    ['/projects/project', '/comparisons/contract-run/results'],
  ]);
});

test('only exact no-score409 becomes absence; access and network errors remain errors', async () => {
  const absent = Object.assign(new Error('No stored score revision is available'), { status: 409 });
  const api = compile('apps/web/src/lib/benchmark-results.ts', {
    './benchmark': {
      benchmarkGet: async (_, suffix) => {
        if (!suffix.endsWith('/results')) return comparison();
        throw absent;
      },
      benchmarkPath: (base) => base,
    },
  });
  assert.equal((await api.loadBenchmarkResults('/projects/project', 'contract-run')).score, null);
  const denied = helpers(async (_, suffix) => {
    if (!suffix.endsWith('/results')) return comparison();
    throw Object.assign(new Error('Access denied'), { status: 403 });
  });
  await assert.rejects(
    denied.loadBenchmarkResults('/projects/project', 'contract-run'),
    /Access denied/,
  );
  const failed = helpers(async () => {
    throw new Error('Network unavailable');
  });
  await assert.rejects(
    failed.loadBenchmarkResults('/projects/project', 'contract-run'),
    /Network unavailable/,
  );
});

test('rejects a score from a different immutable protocol or origin', async () => {
  for (const field of ['protocol_sha256', 'origin']) {
    const score = stored();
    score.projection[field] = 'different';
    const api = helpers(async (_, suffix) => (suffix.endsWith('/results') ? score : comparison()));
    await assert.rejects(
      api.loadBenchmarkResults('/projects/project', 'contract-run'),
      /does not match/,
    );
  }
});

test('export links bind the displayed revision and encode project-run input', () => {
  const url = utilities.benchmarkResultExport(
    '/projects/project',
    'run/unsafe',
    'revision?unsafe',
    'json',
  );
  assert.equal(
    url,
    '/api/v1/projects/project/workspace/benchmarks/comparisons/run%2Funsafe/exports/json?score_revision_id=revision%3Funsafe',
  );
});

test('rejects a non-null primary without a stored approved review state', async () => {
  const score = stored();
  score.projection.models[0].primary = {
    earned_points: '40.5',
    possible_points: '81',
    percent: '50.00',
  };
  const api = helpers(async (_, suffix) => (suffix.endsWith('/results') ? score : comparison()));
  await assert.rejects(
    api.loadBenchmarkResults('/projects/project', 'contract-run'),
    /requires a stored approved/,
  );
});

test('unknown cost is distinct from actual recorded zero and duration stays measured', () => {
  assert.equal(utilities.recordedCost(null), 'Unknown');
  assert.equal(utilities.recordedCost(0), '$0.00');
  assert.equal(utilities.recordedCost(125000), '$0.125');
  assert.equal(utilities.measuredDuration(null), 'Unknown');
  assert.equal(utilities.measuredDuration(1500), '1.5 s');
});

test('unreviewed stored observations show diagnostics while primary remains unavailable', () => {
  const html = render();
  assert.match(html, /Fictional software run/);
  assert.match(html, /exact-contract-model/);
  assert.match(html, /Revision 7/);
  assert.match(html, /pending first review/);
  assert.match(html, /Reviewed primary/);
  assert.match(html, /Unavailable/);
  assert.match(html, /40.5 \/ 81/);
  assert.match(html, /No ranking or winner is inferred/);
  assert.match(html, /Unknown/);
  assert.match(html, /score_revision_id=stored-score-revision/);
  assert.doesNotMatch(html, /UI MOCKUP|Design preview|expected_criteria/);
});

test('reviewed primary is displayed only when present in the stored projection', () => {
  const score = stored();
  score.projection.models[0].primary = {
    earned_points: '40.5',
    possible_points: '81',
    percent: '50.00',
  };
  score.projection.complete = true;
  score.review_state = 'approved';
  score.reviews = 2;
  const html = render(score);
  assert.match(html, /Reviewed publication/);
  assert.match(html, /2 recorded decisions/);
  assert.match(html, /50.00%/);
});

test('absent score shows no invented measurement or unbound export', () => {
  const html = render(null);
  assert.match(html, /No stored score revision yet/);
  assert.match(html, /No scores are generated by this page/);
  assert.doesNotMatch(html, /score_revision_id=|40.5|50.00%/);
});

test('stale policy and denied access clear score, evidence and exports; network error is distinct', () => {
  for (const status of [401, 403, 404, 409]) {
    assert.equal(
      utilities.benchmarkResultsAccessInvalid(Object.assign(new Error('Unavailable'), { status })),
      true,
    );
  }
  assert.equal(utilities.benchmarkResultsAccessInvalid(new Error('Network unavailable')), false);
  assert.equal(
    utilities.benchmarkResultsAccessInvalid(
      Object.assign(new Error('Server error'), { status: 502 }),
    ),
    false,
  );
  const html = render(stored(), {
    accessInvalid: true,
    loaded: false,
    error: 'Source review is no longer current',
  });
  assert.match(html, /Access unavailable/);
  assert.match(html, /Evidence is unavailable until current access and policy are verified/);
  assert.doesNotMatch(html, /40.5|score_revision_id=|Evidence remains explicitly requested/);
  const network = render(stored(), { error: 'Network unavailable' });
  assert.match(network, /Previously loaded revision remains below/);
});

test('actual backend-shaped qualification fixture stays separate from comparison', () => {
  const fixture = JSON.parse(
    readFileSync('contracts/fixtures/benchmark-qualification-evidence-response.json', 'utf8'),
  );
  assert.match(fixture.fixture_notice, /Manufactured contract fixture/);
  const evidence = fixture.data;
  const html = renderToStaticMarkup(React.createElement(QualificationEvidenceReport, { evidence }));
  assert.match(html, /No comparison admission/);
  assert.match(html, /No official primary/);
  assert.match(html, /do not measure a candidate model/);
  assert.match(html, /criterion-1/);
  assert.match(html, /non_root_readonly_no_egress_cgroups/);
  assert.match(html, /fresh_actor/);
  assert.doesNotMatch(html, /score_revision_id=/);
  for (const trial of evidence.qualifications[0].trials) trial.public_capture = null;
  evidence.qualifications[0].trials[0].controls = null;
  const historical = renderToStaticMarkup(
    React.createElement(QualificationEvidenceReport, { evidence }),
  );
  assert.match(historical, /No public output capture was persisted/);
  assert.match(historical, /Missing evidence is not reconstructed/);
  assert.match(historical, /Isolation control observations were not retained/);
  assert.doesNotMatch(historical, /criterion-1/);
});

test('public output text remains escaped even with adversarial HTML', () => {
  const evidence = JSON.parse(
    readFileSync('contracts/fixtures/benchmark-qualification-evidence-response.json', 'utf8'),
  ).data;
  // A deliberately changed presentation fixture, not a valid native seal.
  evidence.qualifications[0].trials[0].public_capture.outputs[0].text = '<script>unsafe</script>';
  const html = renderToStaticMarkup(React.createElement(QualificationEvidenceReport, { evidence }));
  assert.match(html, /&lt;script&gt;unsafe&lt;\/script&gt;/);
  assert.doesNotMatch(html, /<script>/);
});
