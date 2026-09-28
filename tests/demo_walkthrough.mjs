// Creates a retained, explicitly synthetic morning walkthrough through real OIDC and APIs.
import { chromium } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';

const origin = 'http://127.0.0.1:3202';
const accounts = readFileSync('.local/demo-accounts.md', 'utf8');
const ids = JSON.parse(readFileSync('.local/demo-identities.json', 'utf8'));
const project = JSON.parse(
  execFileSync(
    'python3',
    [
      'scripts/local.py',
      'demo-new',
      '--name',
      'ADI Anvil morning fixtures ' + new Date().toISOString(),
    ],
    { encoding: 'utf8' },
  ),
).project_id;
const browser = await chromium.launch({
  headless: true,
  ...(process.env.CI ? {} : { channel: 'chrome' }),
});
const contexts = {};
const folder = 'artifacts/morning-demo';
mkdirSync(folder, { recursive: true });
function assert(value, message) {
  if (!value) throw new Error(message);
}
async function api(who, path, method = 'GET', body, version) {
  const csrf =
    (await contexts[who].cookies()).find((cookie) => cookie.name === 'anvil_csrf')?.value || '';
  const response = await contexts[who].request.fetch(
    origin + '/api/v1/projects/' + project + path,
    {
      method,
      data: body,
      headers: {
        Origin: origin,
        'X-CSRF-Token': csrf,
        'Idempotency-Key': randomUUID(),
        ...(version ? { 'If-Match': String(version) } : {}),
      },
    },
  );
  assert(response.ok(), `${method} ${path} returned ${response.status()}`);
  return (await response.json()).data;
}
async function move(who, collection, record, action, body = {}) {
  return api(who, `/${collection}/${record.id}/${action}`, 'POST', body, record.row_version);
}
async function approve(who, collection, record, purpose) {
  return move(who, collection, record, 'decisions', {
    purpose,
    decision: 'approve',
    rationale:
      'Distinct local synthetic identity exercise only. Scripted fixture review; no expert, model-performance or paid authorization claim.',
  });
}
async function until(check, label) {
  const deadline = Date.now() + 60000;
  while (Date.now() < deadline) {
    const result = await check();
    if (result) return result;
    await new Promise((resolve) => setTimeout(resolve, 300));
  }
  throw new Error(label + ' did not become ready within 60 seconds');
}
try {
  for (const who of [
    'researcher',
    'advisor',
    'product-owner',
    'data-engineer',
    'reviewer-1',
    'reviewer-2',
    'sales',
    'admin-1',
  ]) {
    const context = await browser.newContext();
    contexts[who] = context;
    const page = await context.newPage();
    await page.goto(origin);
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
  let objective = await api('researcher', '/objectives', 'POST', {
    title: 'Synthetic commercial-constraint walkthrough',
    origin: 'adi_initiated',
    entry_type: 'capability',
    hypothesis: 'Supplied hard constraints are preserved in recommendations.',
    business_context:
      'Three original synthetic cases demonstrate local evaluation and review mechanics only.',
    measurement_plan:
      'Three original cases, two deterministic fixture candidates, one attempt each. Independent scripted 4/4/4 or 4/0/4 judgments and critical overrides verify the pipeline. No measured model performance.',
    researcher_id: ids.researcher,
    advisor_id: ids.advisor,
    product_owner_id: ids['product-owner'],
  });
  objective = await move('researcher', 'objectives', objective, 'submit');
  for (const [who, purpose] of [
    ['researcher', 'research'],
    ['advisor', 'advisor'],
    ['product-owner', 'scope'],
  ])
    objective = await approve(who, 'objectives', objective, purpose);
  const cases = await api('data-engineer', '/fixtures/import', 'POST', {
    case_ids: ['MKT-001', 'FIN-001', 'STR-001'],
    reviewer_id: ids['reviewer-1'],
    advisor_id: ids.advisor,
  });
  for (const source of cases)
    for (const [operation, destination] of [
      ['managed_evaluation', 'local_fixture'],
      ['report_sharing', 'internal_fixture'],
    ]) {
      await api(
        'product-owner',
        `/cases/${source.id}/rights`,
        'POST',
        {
          operation,
          destination,
          status: 'approved',
          evidence:
            'Independent local synthetic-source review for this walkthrough and internal aggregate downloads only. No provider processing or external customer distribution.',
        },
        source.row_version,
      );
    }
  for (let rubric of await api('data-engineer', '/rubrics')) {
    rubric = await move('data-engineer', 'rubrics', rubric, 'submit');
    rubric = await approve('reviewer-1', 'rubrics', rubric, 'content');
    await approve('advisor', 'rubrics', rubric, 'calibration');
  }
  const tasks = [];
  for (let task of await api('data-engineer', '/tasks')) {
    task = await move('data-engineer', 'tasks', task, 'submit');
    task = await approve('reviewer-1', 'tasks', task, 'content');
    task = await approve('advisor', 'tasks', task, 'research');
    tasks.push(await move('data-engineer', 'tasks', task, 'publish'));
  }
  let suite = await api('researcher', '/suites', 'POST', {
    title: 'Three original business-case fixtures',
    objective_revision_id: objective.current_revision_id,
    task_revision_ids: tasks.map((task) => task.current_revision_id),
    selection_method:
      'Three supplied original synthetic fixtures; convenience sample for application verification.',
    exposure_note:
      'Known development cases and predetermined candidate outputs, not independent expert or model-performance evidence.',
    planned_source_count: 200,
    advisor_id: ids.advisor,
  });
  suite = await move('researcher', 'suites', suite, 'submit');
  suite = await approve('advisor', 'suites', suite, 'technical');
  suite = await move('researcher', 'suites', suite, 'freeze');
  let protocol = await api('researcher', '/protocols', 'POST', {
    title: 'Six illustrative episodes with independent scripted review',
    objective_revision_id: objective.current_revision_id,
    suite_revision_id: suite.current_revision_id,
    candidates: ['fixture-correct', 'fixture-constraint-blind'],
    reviewer_ids: [ids['reviewer-1'], ids['reviewer-2']],
    adjudicator_id: ids.adjudicator,
    advisor_id: ids.advisor,
    comparison_policy:
      'Same supplied actor artifacts and frozen task versions; descriptive fixture mechanics only, no model ranking.',
    pass_policy:
      'Frozen weighted rubric; hard-constraint critical violation overrides numeric pass. Both independent reviews required.',
    mode: 'fixture',
  });
  protocol = await move('researcher', 'protocols', protocol, 'submit');
  protocol = await approve('advisor', 'protocols', protocol, 'technical');
  let run = await api('researcher', '/runs', 'POST', {
    protocol_revision_id: protocol.current_revision_id,
  });
  await move('researcher', 'runs', run, 'launch');
  run = await until(async () => {
    const row = await api('researcher', '/runs/' + run.id);
    return row.episodes.length === 6 &&
      row.episodes.every((episode) => episode.state === 'awaiting_review')
      ? row
      : null;
  }, 'Fixture capture');
  let promotionFailure;
  for (const episode of run.episodes)
    for (const who of ['reviewer-1', 'reviewer-2']) {
      const detail = await api(who, '/reviews/' + episode.id);
      const output = JSON.parse(detail.output);
      const bad = ['discount_20', 'C', 'West'].includes(output.selected_option);
      if (output.selected_option === 'discount_20') promotionFailure = episode.id;
      const quote = '"selected_option": "' + output.selected_option + '"';
      const numberKey =
        'revenue' in output.options[0]
          ? 'revenue'
          : 'debt_service' in output.options[0]
            ? 'debt_service'
            : 'quarterly_contribution_after_fixed_cost';
      const calculation = JSON.stringify(numberKey) + ': ' + output.options[0][numberKey];
      await api(
        who,
        `/episodes/${episode.id}/assessments`,
        'POST',
        {
          scores: { R1: 4, R2: bad ? 0 : 4, R3: 4 },
          critical: bad ? detail.rubric.critical_rules : [],
          evidence: { R1: calculation, R2: quote, R3: output.limitations },
          rationale:
            'Scripted local fixture vector for application verification, not an expert-calibrated model judgment.',
        },
        detail.row_version,
      );
    }
  run = await until(async () => {
    const row = await api('researcher', '/runs/' + run.id);
    return row.state === 'reviewed' ? row : null;
  }, 'Durable review finalization');
  assert(
    run.episodes.filter((episode) => episode.outcome === 'pass').length === 3,
    'Expected three fixture passes',
  );
  assert(
    run.episodes.reduce((sum, episode) => sum + Number(episode.score), 0) / 6 === 85,
    'Expected fixture mean85',
  );
  const evidence = await api('researcher', `/episodes/${promotionFailure}/evidence`);
  let finding = await api('researcher', '/findings', 'POST', {
    title: 'Observed promotion margin violation — illustrative',
    episode_id: promotionFailure,
    observation:
      'The final output chooses the 20% discount despite the supplied 30% gross-margin floor.',
    hypothesis:
      'This observable output is consistent with failure to preserve a stated constraint; internal causal reasoning is unknown.',
    alternatives: ['Predetermined fixture behavior; not a measured model failure.'],
    confidence: 'high',
    criterion: 'R2',
    output_quote: '"selected_option": "discount_20"',
    capability: 'constraint_preservation',
    advisor_id: ids.advisor,
  });
  assert(evidence.capabilities.includes('constraint_preservation'), 'Capability binding missing');
  finding = await move('researcher', 'findings', finding, 'submit');
  finding = await approve('advisor', 'findings', finding, 'technical');
  let report = await api('researcher', '/reports', 'POST', {
    title: 'Illustrative three-case diagnostic — internal walkthrough',
    run_id: run.id,
    finding_revision_ids: [finding.current_revision_id],
    advisor_id: ids.advisor,
    reviewer_id: ids['reviewer-1'],
    product_owner_id: ids['product-owner'],
    audience: 'internal_fixture',
  });
  report = await move('researcher', 'reports', report, 'submit');
  for (const [who, purpose] of [
    ['advisor', 'technical'],
    ['reviewer-1', 'domain'],
    ['product-owner', 'audience'],
    ['product-owner', 'release'],
  ])
    report = await approve(who, 'reports', report, purpose);
  await api('researcher', `/reports/${report.id}/build`, 'POST', {}, report.row_version);
  const kit = (await api('sales', '/sales-kits')).find(
    (item) => item.content.report_revision_id === report.current_revision_id,
  );
  assert(kit?.lifecycle === 'approved', 'Approved kit missing');
  for (const name of [
    'sales-kit.pdf',
    'sales-kit.html',
    'evidence.zip',
    'email-draft.txt',
    'internal-brief.txt',
  ]) {
    const response = await contexts.sales.request.get(
      origin + `/api/v1/projects/${project}/sales-kits/${kit.id}/download/${name}`,
    );
    assert(response.ok(), 'Approved download failed: ' + name);
    writeFileSync(folder + '/' + name, await response.body());
  }
  const pending = await api('researcher', '/runs', 'POST', {
    protocol_revision_id: protocol.current_revision_id,
  });
  await move('researcher', 'runs', pending, 'launch');
  await until(async () => {
    const row = await api('researcher', '/runs/' + pending.id);
    return (
      row.episodes.length === 6 &&
      row.episodes.every((episode) => episode.state === 'awaiting_review')
    );
  }, 'Manual-review practice run');
  await api('admin-1', '/graph/rebuild', 'POST', {});
  const page = await contexts.researcher.newPage();
  await page.setViewportSize({ width: 1440, height: 1000 });
  for (const section of ['cases', 'runs', 'diagnostics', 'reports']) {
    await page.goto(origin + `/p/${project}/${section}`);
    await page.getByRole('button', { name: 'Sign out' }).waitFor();
    if (section === 'reports')
      await page.getByText('Mean reviewed score / 100', { exact: true }).waitFor();
    if (section === 'cases') await page.getByText('Actual source cases', { exact: true }).waitFor();
    if (section === 'diagnostics')
      await page.getByRole('group', { name: 'Version-bound evidence graph' }).waitFor();
    await page.screenshot({ path: `${folder}/${section}.png`, fullPage: true });
  }
  const result = {
    status: 'ready',
    origin: 'illustrative',
    project_id: project,
    url: `${origin}/p/${project}/objectives`,
    report_id: report.id,
    kit_id: kit.id,
    reviewed_run_id: run.id,
    pending_practice_run_id: pending.id,
    source_cases: 3,
    source_families: 3,
    valid_episodes: 6,
    passes: 3,
    failures: 3,
    mean_score: 85,
    pending_manual_reviews: 6,
    model_performance: 'not_measured',
    live_model_calls: 0,
    real_email_sent: false,
    artifacts: folder,
  };
  writeFileSync('.local/morning-demo.json', JSON.stringify(result, null, 2), { mode: 0o600 });
  writeFileSync(folder + '/walkthrough.json', JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result));
} finally {
  for (const context of Object.values(contexts)) await context.close();
  await browser.close();
}
