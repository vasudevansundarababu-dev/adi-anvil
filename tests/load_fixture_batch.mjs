// Explicit local throughput rehearsal. Reuses three synthetic cases, never a model benchmark.
import { chromium } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { performance } from 'node:perf_hooks';

const started = performance.now();
const accounts = readFileSync('.local/demo-accounts.md', 'utf8');
const ids = JSON.parse(readFileSync('.local/demo-identities.json', 'utf8'));
const project = JSON.parse(
  execFileSync(
    'python3',
    ['scripts/local.py', 'demo-new', '--name', 'Synthetic 400-episode fixture throughput'],
    { encoding: 'utf8' },
  ),
).project_id;
const base = `http://127.0.0.1:3202/api/v1/projects/${project}`;
const browser = await chromium.launch({
  headless: true,
  ...(process.env.CI ? {} : { channel: 'chrome' }),
});
const contexts = {};
function assert(condition, message) {
  if (!condition) throw new Error(message);
}
async function command(who, path, method = 'GET', body, version, key = randomUUID()) {
  const context = contexts[who];
  const csrf = (await context.cookies()).find((cookie) => cookie.name === 'anvil_csrf')?.value;
  const response = await context.request.fetch(base + path, {
    method,
    data: body,
    headers: {
      Origin: 'http://127.0.0.1:3202',
      'X-CSRF-Token': csrf || '',
      'Idempotency-Key': key,
      ...(version ? { 'If-Match': String(version) } : {}),
    },
  });
  assert(response.ok(), `${method} ${path} failed with status ${response.status()}`);
  return (await response.json()).data;
}
async function transition(who, kind, record, action, body = {}) {
  return command(who, `/${kind}/${record.id}/${action}`, 'POST', body, record.row_version);
}
async function approve(who, kind, record, purpose) {
  return transition(who, kind, record, 'decisions', {
    purpose,
    decision: 'approve',
    rationale:
      'Independent synthetic throughput-test approval. No live execution or measured model-performance claim.',
  });
}
try {
  for (const who of ['researcher', 'advisor', 'product-owner', 'data-engineer', 'reviewer-1']) {
    const context = await browser.newContext();
    contexts[who] = context;
    const page = await context.newPage();
    await page.goto('http://127.0.0.1:3202');
    await page.getByRole('link', { name: 'Sign in with Keycloak' }).click();
    await page.locator('#username').fill(who);
    await page.locator('#password').fill(
      accounts
        .split('\n')
        .find((line) => line.startsWith('- ' + who + ':'))
        .split('`')[1],
    );
    await page.locator('#kc-login').click();
    await page.getByRole('button', { name: 'Sign out' }).waitFor();
  }
  let objective = await command('researcher', '/objectives', 'POST', {
    title: 'Synthetic fixture throughput only — three reused cases',
    origin: 'adi_initiated',
    entry_type: 'capability',
    hypothesis:
      'The local worker can durably capture 400 deterministic outputs while keeping the UI responsive.',
    business_context:
      'Application throughput verification only. Not a frontier-model or independent-case study.',
    measurement_plan:
      'Three original synthetic cases and families, 200 deliberately duplicated task variants, two fixture candidates. Measure queue/UI/restart behavior only. All scores remain pending human review.',
    researcher_id: ids.researcher,
    advisor_id: ids.advisor,
    product_owner_id: ids['product-owner'],
  });
  objective = await transition('researcher', 'objectives', objective, 'submit');
  for (const [who, purpose] of [
    ['researcher', 'research'],
    ['advisor', 'advisor'],
    ['product-owner', 'scope'],
  ])
    objective = await approve(who, 'objectives', objective, purpose);
  const sources = await command('data-engineer', '/fixtures/import', 'POST', {
    case_ids: ['MKT-001', 'FIN-001', 'STR-001'],
    reviewer_id: ids['reviewer-1'],
    advisor_id: ids.advisor,
  });
  for (const source of sources)
    for (const [operation, destination] of [
      ['managed_evaluation', 'local_fixture'],
      ['report_sharing', 'internal_fixture'],
    ]) {
      await command(
        'product-owner',
        `/cases/${source.id}/rights`,
        'POST',
        {
          operation,
          destination,
          status: 'approved',
          evidence:
            'Independent review of original synthetic fixtures for local throughput testing and internal aggregate reporting only.',
        },
        source.row_version,
      );
    }
  for (let rubric of await command('data-engineer', '/rubrics')) {
    rubric = await transition('data-engineer', 'rubrics', rubric, 'submit');
    rubric = await approve('reviewer-1', 'rubrics', rubric, 'content');
    await approve('advisor', 'rubrics', rubric, 'calibration');
  }
  const templates = await command('researcher', '/tasks');
  const variants = [];
  for (let index = 0; index < 200; index++) {
    let task = await command('researcher', '/tasks', 'POST', {
      ...templates[index % 3].content,
      title: `Synthetic repeated throughput variant ${index + 1}`,
    });
    task = await transition('researcher', 'tasks', task, 'submit');
    task = await approve('reviewer-1', 'tasks', task, 'content');
    task = await approve('advisor', 'tasks', task, 'research');
    task = await transition('data-engineer', 'tasks', task, 'publish');
    variants.push(task.current_revision_id);
    if (variants.length % 25 === 0)
      console.log(
        `Qualified ${variants.length}/200 synthetic task variants; source cases remain three.`,
      );
  }
  let suite = await command('researcher', '/suites', 'POST', {
    title: 'Synthetic repeated-variant throughput suite',
    objective_revision_id: objective.current_revision_id,
    task_revision_ids: variants,
    selection_method:
      'Repeat the three original cases solely to exercise bounded local throughput.',
    exposure_note:
      'Known development fixtures; repeated variants are not independent cases or model-performance evidence.',
    advisor_id: ids.advisor,
    planned_source_count: 3,
  });
  suite = await transition('researcher', 'suites', suite, 'submit');
  suite = await approve('advisor', 'suites', suite, 'technical');
  suite = await transition('researcher', 'suites', suite, 'freeze');
  let protocol = await command('researcher', '/protocols', 'POST', {
    title: '400 deterministic episodes, no live inference',
    objective_revision_id: objective.current_revision_id,
    suite_revision_id: suite.current_revision_id,
    candidates: ['fixture-correct', 'fixture-constraint-blind'],
    reviewer_ids: [ids['reviewer-1'], ids['reviewer-2']],
    adjudicator_id: ids.adjudicator,
    advisor_id: ids.advisor,
    comparison_policy:
      'This is a repeated-fixture throughput exercise, not a comparison of real models or independent samples.',
    pass_policy: 'No automatic judgments. Every output stays pending assigned human review.',
    mode: 'fixture',
  });
  protocol = await transition('researcher', 'protocols', protocol, 'submit');
  protocol = await approve('advisor', 'protocols', protocol, 'technical');
  const run = await command('researcher', '/runs', 'POST', {
    protocol_revision_id: protocol.current_revision_id,
  });
  const page = await contexts.researcher.newPage();
  await page.goto(`http://127.0.0.1:3202/p/${project}/runs`);
  await page.getByRole('heading', { name: 'Run console', exact: true }).waitFor();
  const executionStart = performance.now();
  const key = randomUUID();
  await command('researcher', `/runs/${run.id}/launch`, 'POST', {}, run.row_version, key);
  await command('researcher', `/runs/${run.id}/launch`, 'POST', {}, run.row_version, key);
  await page.getByRole('button', { name: 'Refresh', exact: true }).click();
  const uiStarted = performance.now();
  await page.getByRole('button', { name: 'Inspect episodes', exact: true }).click();
  await page.locator('tbody tr').nth(399).waitFor({ state: 'attached' });
  const tableReadyMs = performance.now() - uiStarted;
  const during = await command('researcher', `/runs/${run.id}`);
  const capturedDuringUi = during.episodes.filter(
    (episode) => episode.invocation_count === 1,
  ).length;
  await page.bringToFront();
  const frameTiming = await page.evaluate(
    () =>
      new Promise((resolve) => {
        const gaps = [];
        let previous = performance.now();
        function frame(now) {
          gaps.push(now - previous);
          previous = now;
          if (gaps.length === 120)
            resolve({
              frames: 120,
              max_gap_ms: Math.max(...gaps),
              duration_ms: gaps.reduce((a, b) => a + b, 0),
            });
          else requestAnimationFrame(frame);
        }
        requestAnimationFrame(frame);
      }),
  );
  assert(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    'Run console overflowed the viewport',
  );
  mkdirSync('artifacts/test-runs', { recursive: true });
  await page.screenshot({ path: 'artifacts/test-runs/load-run-console.png' });
  const beforeRestart = (await command('researcher', `/runs/${run.id}`)).episodes.filter(
    (episode) => episode.invocation_count === 1,
  ).length;
  const restartStarted = performance.now();
  execFileSync('python3', ['scripts/local.py', 'worker-restart'], { stdio: 'pipe' });
  let firstProgressMs = null,
    final;
  const deadline = performance.now() + 10 * 60 * 1000;
  let lastBucket = -1;
  while (performance.now() < deadline) {
    final = await command('researcher', `/runs/${run.id}`);
    const captured = final.episodes.filter((episode) => episode.invocation_count === 1).length;
    if (captured > beforeRestart && firstProgressMs === null)
      firstProgressMs = performance.now() - restartStarted;
    const bucket = Math.floor(captured / 50);
    if (bucket !== lastBucket) {
      console.log(`Captured ${captured}/400 fixture outputs; reviews remain pending.`);
      lastBucket = bucket;
    }
    if (final.episodes.every((episode) => episode.state === 'awaiting_review')) break;
    assert(
      !final.episodes.some((episode) => episode.state === 'failed_operational'),
      'Fixture worker failed operationally',
    );
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  assert(
    final.episodes.length === 400 &&
      final.episodes.every(
        (episode) =>
          episode.state === 'awaiting_review' &&
          episode.invocation_count === 1 &&
          episode.score === null,
      ),
    'Incomplete or duplicated fixture batch',
  );
  assert(
    firstProgressMs !== null && firstProgressMs < 90000,
    'Worker restart recovery exceeded 90 seconds',
  );
  const result = {
    status: 'passed',
    project_id: project,
    run_id: run.id,
    origin: 'illustrative',
    independent_source_cases: 3,
    source_families: 3,
    repeated_task_variants: 200,
    episodes: 400,
    pending_human_reviews: 400,
    model_performance: 'not_measured',
    live_model_calls: 0,
    setup_seconds: (executionStart - started) / 1000,
    execution_seconds: (performance.now() - executionStart) / 1000,
    ui_table_ready_ms: tableReadyMs,
    outputs_captured_during_ui_probe: capturedDuringUi,
    ui_probe_overlapped_execution: capturedDuringUi < 400,
    frame_timing: frameTiming,
    first_progress_after_restart_ms: firstProgressMs,
    duplicate_invocations: 0,
  };
  writeFileSync(
    'artifacts/test-runs/load-fixture-performance.json',
    JSON.stringify(result, null, 2),
  );
  console.log(JSON.stringify(result));
} finally {
  await browser.close();
}
