import { test, expect, Browser, BrowserContext } from '@playwright/test';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { randomUUID } from 'node:crypto';
import { execFileSync } from 'node:child_process';
let project: string;
let base: string;
const accounts = readFileSync('.local/demo-accounts.md', 'utf8');
const ids = JSON.parse(readFileSync('.local/demo-identities.json', 'utf8'));
async function login(browser: Browser, name: string) {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto('/');
  await page.getByRole('link', { name: 'Sign in with Keycloak' }).click();
  await page.locator('#username').fill(name);
  const password = accounts
    .split('\n')
    .find((l) => l.startsWith('- ' + name + ':'))!
    .split('`')[1];
  await page.locator('#password').fill(password);
  await page.locator('#kc-login').click();
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible();
  return context;
}
async function call(
  ctx: BrowserContext,
  path: string,
  method = 'GET',
  body?: unknown,
  version?: number,
  key?: string,
) {
  const cookies = await ctx.cookies();
  const csrf = cookies.find((c) => c.name === 'anvil_csrf')?.value || '';
  const r = await ctx.request.fetch(base + path, {
    method,
    data: body,
    headers: {
      Origin: 'http://127.0.0.1:3202',
      'X-CSRF-Token': csrf,
      'Idempotency-Key': key || randomUUID(),
      ...(version ? { 'If-Match': String(version) } : {}),
    },
  });
  const result = await r.json();
  expect(r.status(), JSON.stringify(result)).toBeLessThan(300);
  return result.data;
}
async function transition(ctx: BrowserContext, col: string, r: any, action: string, body = {}) {
  const latest = await call(ctx, `/${col}/${r.id}`);
  return call(ctx, `/${col}/${r.id}/${action}`, 'POST', body, latest.row_version);
}
async function approve(ctx: BrowserContext, col: string, r: any, purpose: string) {
  return transition(ctx, col, r, 'decisions', {
    purpose,
    decision: 'approve',
    rationale: 'Independent synthetic fixture review for local pipeline verification only.',
  });
}

test('real OIDC, qualified six-episode fixture journey, independent reviews and isolation', async ({
  browser,
}) => {
  project = JSON.parse(
    execFileSync(
      'python3',
      ['scripts/local.py', 'demo-new', '--name', 'Synthetic browser acceptance ' + Date.now()],
      { encoding: 'utf8' },
    ),
  ).project_id;
  base = '/api/v1/projects/' + project;
  const contexts: Record<string, BrowserContext> = {};
  for (const name of [
    'researcher',
    'advisor',
    'product-owner',
    'data-engineer',
    'reviewer-1',
    'reviewer-2',
    'adjudicator',
    'sales',
    'admin-1',
    'admin-2',
    'outsider',
  ])
    contexts[name] = await login(browser, name);
  const R = contexts.researcher,
    A = contexts.advisor,
    P = contexts['product-owner'],
    D = contexts['data-engineer'];
  const objective = await call(R, '/objectives', 'POST', {
    title: 'Synthetic commercial-constraint diagnostic ' + Date.now(),
    origin: 'adi_initiated',
    entry_type: 'capability',
    hypothesis: 'Supplied hard constraints are preserved in recommendations.',
    business_context: 'Original synthetic fixture exercise; no measured model performance.',
    measurement_plan:
      'Three original cases; two deterministic candidates; one attempt each; anchored rubric and critical overrides; descriptive results only.',
    researcher_id: ids.researcher,
    advisor_id: ids.advisor,
    product_owner_id: ids['product-owner'],
  });
  await transition(R, 'objectives', objective, 'submit');
  await approve(R, 'objectives', objective, 'research');
  await approve(A, 'objectives', objective, 'advisor');
  await approve(P, 'objectives', objective, 'scope');
  const imp = {
    case_ids: ['MKT-001', 'FIN-001', 'STR-001'],
    reviewer_id: ids['reviewer-1'],
    advisor_id: ids.advisor,
  };
  const cases = await call(D, '/fixtures/import', 'POST', imp);
  await call(D, '/fixtures/import', 'POST', imp);
  expect(
    (await call(D, '/cases?limit=100')).filter(
      (c: any) => c.content.source_origin === 'original_synthetic_fixture',
    ).length,
  ).toBe(3);
  for (const source of cases)
    await call(
      P,
      `/cases/${source.id}/rights`,
      'POST',
      {
        operation: 'managed_evaluation',
        destination: 'local_fixture',
        status: 'approved',
        evidence:
          'Reviewed original synthetic fixture rights for local pipeline testing only; no external processing.',
      },
      source.row_version,
    );
  for (const rubric of await call(D, '/rubrics'))
    if (rubric.lifecycle === 'draft') {
      await transition(D, 'rubrics', rubric, 'submit');
      await approve(contexts['reviewer-1'], 'rubrics', rubric, 'content');
      await approve(A, 'rubrics', rubric, 'calibration');
    }
  for (const task of await call(D, '/tasks'))
    if (task.lifecycle === 'draft') {
      await transition(D, 'tasks', task, 'submit');
      await approve(contexts['reviewer-1'], 'tasks', task, 'content');
      await approve(A, 'tasks', task, 'research');
      await transition(D, 'tasks', task, 'publish');
    }
  const tasks = await call(R, '/tasks');
  expect(tasks.length).toBe(3);
  const suite = await call(R, '/suites', 'POST', {
    title: 'Three-case original synthetic suite',
    objective_revision_id: objective.current_revision_id,
    task_revision_ids: tasks.map((t: any) => t.current_revision_id),
    selection_method: 'All three supplied original fixtures.',
    exposure_note: 'Known development fixtures; no generalization or faculty validation.',
    advisor_id: ids.advisor,
    planned_source_count: 200,
  });
  await transition(R, 'suites', suite, 'submit');
  await approve(A, 'suites', suite, 'technical');
  await transition(R, 'suites', suite, 'freeze');
  const protocol = await call(R, '/protocols', 'POST', {
    title: 'Deterministic two-candidate pilot',
    objective_revision_id: objective.current_revision_id,
    suite_revision_id: suite.current_revision_id,
    candidates: ['fixture-correct', 'fixture-constraint-blind'],
    reviewer_ids: [ids['reviewer-1'], ids['reviewer-2']],
    adjudicator_id: ids.adjudicator,
    advisor_id: ids.advisor,
    comparison_policy:
      'Same frozen actor inputs, descriptive fixture pipeline checks; no model ranking.',
    pass_policy:
      'Rubric threshold and critical override; all pilot episodes independently double reviewed.',
  });
  await transition(R, 'protocols', protocol, 'submit');
  await approve(A, 'protocols', protocol, 'technical');
  const run = await call(R, '/runs', 'POST', {
    protocol_revision_id: protocol.current_revision_id,
  });
  const launchKey = randomUUID();
  await call(R, `/runs/${run.id}/launch`, 'POST', {}, run.row_version, launchKey);
  await call(R, `/runs/${run.id}/launch`, 'POST', {}, run.row_version, launchKey);
  await expect
    .poll(
      async () => {
        const r = await call(R, `/runs/${run.id}`);
        return r.episodes.filter((e: any) => e.state === 'awaiting_review').length;
      },
      { timeout: 30000 },
    )
    .toBe(6);
  let before = await call(R, `/runs/${run.id}`);
  expect(before.episodes.every((e: any) => e.invocation_count === 1)).toBeTruthy();
  await expect
    .poll(
      async () =>
        (await call(R, '/sales-kits')).some(
          (k: any) => k.content.run_id === run.id && k.content.stage === 'provisional',
        ),
      { timeout: 30000 },
    )
    .toBeTruthy();
  const provisional = (await call(R, '/sales-kits')).find(
    (k: any) => k.content.run_id === run.id && k.content.stage === 'provisional',
  );
  expect(provisional.content.facts.mean_score).toBeNull();
  expect(provisional.content.label).toContain('PROVISIONAL');
  execFileSync('python3', ['scripts/local.py', 'worker-restart']);
  for (const episode of before.episodes) {
    for (const name of ['reviewer-1', 'reviewer-2']) {
      const detail = await call(contexts[name], `/reviews/${episode.id}`);
      expect(JSON.stringify(detail)).not.toContain('candidate_key');
      expect(detail.submitted_assessments).toBeUndefined();
      const output = JSON.parse(detail.output);
      const bad =
        output.constraint_checks.includes('despite') ||
        output.constraint_checks.includes('even though');
      const scores = { R1: 4, R2: bad ? 0 : 4, R3: 4 };
      const quote = '"selected_option": "' + output.selected_option + '"';
      await call(
        contexts[name],
        `/episodes/${episode.id}/assessments`,
        'POST',
        {
          scores,
          critical: bad ? detail.rubric.critical_rules : [],
          evidence: { R1: quote, R2: quote, R3: quote },
          rationale: 'Scripted independent synthetic judgment; fixture verification only.',
        },
        detail.row_version,
      );
    }
  }
  await expect
    .poll(async () => (await call(R, `/runs/${run.id}`)).state, { timeout: 30000 })
    .toBe('reviewed');
  const final = await call(R, `/runs/${run.id}`);
  expect(final.episodes.filter((e: any) => e.outcome === 'pass').length).toBe(3);
  expect(final.episodes.reduce((s: number, e: any) => s + Number(e.score), 0) / 6).toBe(85);
  expect(final.episodes.every((e: any) => e.invocation_count === 1)).toBeTruthy();
  for (const source of cases)
    await call(
      P,
      `/cases/${source.id}/rights`,
      'POST',
      {
        operation: 'report_sharing',
        destination: 'internal_fixture',
        status: 'approved',
        evidence:
          'Reviewed synthetic aggregate-only internal draft sharing. No raw case redistribution or external customer delivery.',
      },
      source.row_version,
    );
  const findingEvidence = await call(R, `/episodes/${final.episodes[0].id}/evidence`);
  const finding = await call(R, '/findings', 'POST', {
    title: 'Reviewed illustrative output observation',
    episode_id: final.episodes[0].id,
    observation:
      'The scripted fixture output contains the selected option shown in the quoted evidence.',
    hypothesis: null,
    alternatives: ['Predetermined fixture behavior; no inference about model reasoning.'],
    confidence: 'unknown',
    criterion: 'R2',
    output_quote: '"selected_option": "' + JSON.parse(findingEvidence.output).selected_option + '"',
    capability: 'constraint_preservation',
    advisor_id: ids.advisor,
  });
  await transition(R, 'findings', finding, 'submit');
  await approve(A, 'findings', finding, 'technical');
  const report = await call(R, '/reports', 'POST', {
    title: 'Reviewed synthetic diagnostic',
    run_id: run.id,
    finding_revision_ids: [finding.current_revision_id],
    advisor_id: ids.advisor,
    reviewer_id: ids['reviewer-1'],
    product_owner_id: ids['product-owner'],
    audience: 'internal_fixture',
  });
  await transition(R, 'reports', report, 'submit');
  await approve(A, 'reports', report, 'technical');
  await approve(contexts['reviewer-1'], 'reports', report, 'domain');
  await approve(P, 'reports', report, 'audience');
  await approve(P, 'reports', report, 'release');
  await expect
    .poll(
      async () =>
        (await call(R, '/sales-kits')).some(
          (k: any) =>
            k.content.report_revision_id === report.current_revision_id &&
            k.lifecycle === 'approved',
        ),
      { timeout: 30000 },
    )
    .toBeTruthy();
  await transition(R, 'reports', report, 'build');
  mkdirSync('artifacts/test-runs', { recursive: true });
  for (const name of ['sales-kit.pdf', 'sales-kit.html', 'evidence.zip', 'email-draft.txt']) {
    const download = await contexts.sales.request.get(
      base + `/reports/${report.id}/download/${name}`,
    );
    expect(download.status()).toBe(200);
    writeFileSync('artifacts/test-runs/' + name, await download.body());
  }
  const kit = (await call(contexts.sales, '/sales-kits')).find(
    (k: any) => k.content.report_revision_id === report.current_revision_id,
  );
  expect(kit.content.artifacts['evidence.zip']).toBeTruthy();
  const contact = await call(contexts.sales, '/sales-contacts', 'POST', {
    name: 'Synthetic lab contact',
    email: 'evaluation@lab.invalid',
    organization_label: 'Local fixture lab',
    contact_basis: 'Explicit synthetic test contact for network-free workflow verification only.',
  });
  await call(
    P,
    `/sales-contacts/${contact.id}/decision`,
    'POST',
    { status: 'approved' },
    contact.row_version,
  );
  const sender = await call(contexts['admin-1'], '/fixture-senders', 'POST', {
    name: 'Synthetic accepted sender',
    scenario: 'accepted',
  });
  await call(
    contexts['admin-2'],
    `/fixture-senders/${sender.id}/activate`,
    'POST',
    {},
    sender.row_version,
  );
  const deliveryApproval = await call(P, `/sales-kits/${kit.id}/delivery-approvals`, 'POST', {
    recipient_contact_id: contact.id,
    sender_connection_id: sender.id,
  });
  const mail = await call(contexts.sales, `/sales-kits/${kit.id}/simulate-send`, 'POST', {
    delivery_approval_id: deliveryApproval.id,
    content_hash: deliveryApproval.content_hash,
  });
  await expect
    .poll(async () => (await call(contexts.sales, `/sales-deliveries/${mail.id}`)).status, {
      timeout: 30000,
    })
    .toBe('fixture_accepted');
  expect((await call(contexts.sales, `/sales-deliveries/${mail.id}`)).real_email_sent).toBe(false);
  const graph = await call(R, '/diagnostics');
  expect(graph.nodes.length).toBeGreaterThan(0);
  expect(graph.edges.length).toBeGreaterThan(0);
  const denied = await contexts.sales.request.get(base + '/rubrics');
  expect(denied.status()).toBe(403);
  const outsider = await contexts.outsider.request.get(base + '/objectives/' + objective.id);
  expect(outsider.status()).toBe(404);
  const csrf = await R.request.post(base + '/objectives', { data: {} });
  expect(csrf.status()).toBe(403);
  const page = await R.newPage();
  await page.goto('/p/' + project + '/objectives');
  await expect(
    page.getByRole('heading', { name: 'Research objectives', exact: true }),
  ).toBeVisible();
  mkdirSync('artifacts/test-runs', { recursive: true });
  await page.screenshot({ path: 'artifacts/test-runs/objectives.png', fullPage: true });
  for (const width of [320, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBeTruthy();
    await page.getByRole('button', { name: 'Toggle color theme' }).focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('button', { name: 'Toggle color theme' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await page.screenshot({
      path: `artifacts/test-runs/objectives-dark-${width}.png`,
      fullPage: true,
    });
    await page.keyboard.press('Enter');
  }
  writeFileSync(
    'artifacts/test-runs/journey.json',
    JSON.stringify(
      {
        project_id: project,
        run_id: run.id,
        objective,
        suite,
        protocol,
        report,
        episodes: final.episodes,
      },
      null,
      2,
    ),
  );
  const disputedRun = await call(R, '/runs', 'POST', {
    protocol_revision_id: protocol.current_revision_id,
  });
  await call(R, `/runs/${disputedRun.id}/launch`, 'POST', {}, disputedRun.row_version);
  await expect
    .poll(
      async () =>
        (await call(R, `/runs/${disputedRun.id}`)).episodes.filter(
          (e: any) => e.state === 'awaiting_review',
        ).length,
      { timeout: 30000 },
    )
    .toBe(6);
  const episode = (await call(R, `/runs/${disputedRun.id}`)).episodes[0];
  for (const [name, value] of [
    ['reviewer-1', 4],
    ['reviewer-2', 0],
  ] as const) {
    const detail = await call(contexts[name], `/reviews/${episode.id}`);
    expect(detail.submitted_assessments).toBeUndefined();
    const quote = '"selected_option": "' + JSON.parse(detail.output).selected_option + '"';
    await call(
      contexts[name],
      `/episodes/${episode.id}/assessments`,
      'POST',
      {
        scores: { R1: value, R2: value, R3: value },
        critical: [],
        evidence: { R1: quote, R2: quote, R3: quote },
        rationale: 'Deliberate synthetic disagreement to verify independent adjudication.',
      },
      detail.row_version,
    );
  }
  const disputed = await call(contexts.adjudicator, `/reviews/${episode.id}`);
  expect(disputed.state).toBe('disputed');
  expect(disputed.submitted_assessments).toHaveLength(2);
  const quote = '"selected_option": "' + JSON.parse(disputed.output).selected_option + '"';
  await call(
    contexts.adjudicator,
    `/episodes/${episode.id}/adjudicate`,
    'POST',
    {
      scores: { R1: 4, R2: 4, R3: 4 },
      critical: [],
      evidence: { R1: quote, R2: quote, R3: quote },
      rationale: 'Independent third identity resolves deliberate fixture dispute.',
    },
    disputed.row_version,
  );
  await expect
    .poll(
      async () =>
        (await call(R, `/runs/${disputedRun.id}`)).episodes.find((e: any) => e.id === episode.id)
          .state,
      { timeout: 30000 },
    )
    .toBe('finalized');
  const ambiguous = (await call(R, `/runs/${disputedRun.id}`)).episodes.find(
    (e: any) => e.state === 'awaiting_review',
  );
  for (const decision of ['resume_review', 'invalid']) {
    const detail = await call(contexts['reviewer-1'], `/reviews/${ambiguous.id}`);
    await call(
      contexts['reviewer-1'],
      `/episodes/${ambiguous.id}/review-issues`,
      'POST',
      {
        code: 'ambiguous_reference',
        rationale:
          'Synthetic ambiguous-reference exercise; evidence cannot support a candidate failure.',
      },
      detail.row_version,
    );
    const blocked = await call(contexts.adjudicator, `/reviews/${ambiguous.id}`);
    expect(blocked.state).toBe('review_blocked');
    expect(blocked.issue_resolution_allowed).toBe(true);
    await call(
      contexts.adjudicator,
      `/episodes/${ambiguous.id}/resolve-issue`,
      'POST',
      {
        decision,
        rationale: 'Independent adjudicator records the synthetic evidence validity decision.',
      },
      blocked.row_version,
    );
  }
  await expect
    .poll(
      async () =>
        (await call(R, `/runs/${disputedRun.id}`)).episodes.find((e: any) => e.id === ambiguous.id)
          .state,
      { timeout: 30000 },
    )
    .toBe('finalized');
  const invalid = (await call(R, `/runs/${disputedRun.id}`)).episodes.find(
    (e: any) => e.id === ambiguous.id,
  );
  expect(invalid.outcome).toBe('invalid');
  expect(invalid.score).toBeNull();
  expect(invalid.invocation_count).toBe(1);
  const cancelTarget = await call(R, `/runs/${disputedRun.id}`);
  await call(R, `/runs/${disputedRun.id}/cancel`, 'POST', {}, cancelTarget.row_version);
  const cancelled = await call(R, `/runs/${disputedRun.id}`);
  expect(cancelled.state).toBe('cancelled');
  expect(cancelled.episodes.filter((e: any) => e.state === 'cancelled')).toHaveLength(4);
  expect(cancelled.episodes.every((e: any) => e.invocation_count === 1)).toBeTruthy();
  await call(
    P,
    `/cases/${cases[0].id}/rights`,
    'POST',
    {
      operation: 'report_sharing',
      destination: 'internal_fixture',
      status: 'revoked',
      evidence: 'Synthetic revocation check: previously generated downloads must be blocked.',
    },
    cases[0].row_version,
  );
  expect(
    (
      await contexts.sales.request.get(base + `/reports/${report.id}/download/evidence.zip`)
    ).status(),
  ).toBe(409);
  await call(
    P,
    `/cases/${cases[0].id}/rights`,
    'POST',
    {
      operation: 'report_sharing',
      destination: 'internal_fixture',
      status: 'approved',
      evidence: 'Restored reviewed internal synthetic sharing scope after revocation test.',
    },
    cases[0].row_version,
  );
  const approvedReport = await call(R, `/reports/${report.id}`);
  const successor = await call(
    R,
    `/reports/${report.id}/successor`,
    'POST',
    {
      title: 'Corrected synthetic diagnostic requiring fresh review',
      run_id: run.id,
      finding_revision_ids: [],
      advisor_id: ids.advisor,
      reviewer_id: ids['reviewer-1'],
      product_owner_id: ids['product-owner'],
      audience: 'internal_fixture',
    },
    approvedReport.row_version,
  );
  expect(successor.lifecycle).toBe('draft');
  expect(successor.current_revision_id).not.toBe(report.current_revision_id);
  expect(
    (
      await contexts.sales.request.get(base + `/reports/${report.id}/download/evidence.zip`)
    ).status(),
  ).toBe(409);
  const externalProtocol = await call(R, '/protocols', 'POST', {
    ...protocol.content,
    title: 'Reported result browser import',
    candidates: ['external-reported'],
    mode: 'external_result_import_v1',
  });
  await transition(R, 'protocols', externalProtocol, 'submit');
  await approve(A, 'protocols', externalProtocol, 'technical');
  const externalRun = await call(R, '/runs', 'POST', {
    protocol_revision_id: externalProtocol.current_revision_id,
    external_origin: 'customer_reported',
  });
  const importPage = await D.newPage();
  await importPage.goto('/p/' + project + '/runs');
  await importPage.getByText('Import reported results', { exact: true }).click();
  await importPage.getByLabel('External results manifest').fill(
    JSON.stringify({
      schema_version: 'anvil.external_results.v1',
      run_id: externalRun.id,
      origin: 'customer_reported',
      producer: 'Synthetic browser import exercise',
      executed_at: '2026-09-27T10:00:00Z',
      protocol_hash: null,
      producer_manifest_hash: null,
      incomparability_reasons: ['Synthetic aggregate-only recording; configuration not known.'],
      candidate_descriptor: {
        model_requested: null,
        model_returned: null,
        harness_version: null,
        graph_version: null,
        tools: null,
        parameters: null,
      },
      attempts: [
        {
          task_revision_id: tasks[0].current_revision_id,
          repetition: 1,
          attempt: 1,
          execution_state: 'completed',
          limitations: ['No output supplied; cannot receive an Anvil grade.'],
        },
      ],
    }),
  );
  await importPage.getByRole('button', { name: 'Validate without importing' }).click();
  await expect(importPage.getByText('Batch: validated', { exact: true })).toBeVisible();
  expect((await call(R, `/runs/${externalRun.id}`)).episodes).toHaveLength(0);
  await importPage.getByRole('button', { name: 'Commit this validated manifest' }).click();
  await expect(importPage.getByText('Batch: committed', { exact: true })).toBeVisible();
  const imported = await call(R, `/runs/${externalRun.id}`);
  expect(imported.origin).toBe('customer_reported');
  expect(imported.episodes[0].state).toBe('unscorable');
  expect(imported.episodes[0].score).toBeNull();
  expect(imported.episodes[0].invocation_count).toBe(0);
  const inventory = await call(D, '/imports/validate', 'POST', {
    schema_version: 'anvil.case_import.v1',
    partner_key: 'synthetic-browser-pagination',
    cases: Array.from({ length: 26 }, (_, i) => ({
      external_case_id: 'BROWSER-LOAD-' + i,
      source_version: 'synthetic-v1',
      title: 'Synthetic browser pagination case ' + String(i).padStart(3, '0'),
      subjects: ['synthetic_test_only'],
      source_family_key: 'synthetic-browser-family-' + i,
      artifact_ids: [tasks[0].content.actor_artifact_ids[0]],
      provenance: { origin: 'synthetic_browser_load_test', faculty_reviewed: false },
      readiness: [],
      rights_declarations: [],
    })),
  });
  expect(inventory.status).toBe('validated');
  await call(D, '/imports/' + inventory.id + '/commit', 'POST', {
    manifest_hash: inventory.manifest_hash,
  });
  await importPage.goto('/p/' + project + '/cases');
  await expect(importPage.getByText('25 of 29 matching records loaded')).toBeVisible();
  await expect(
    importPage.getByText('Actual source cases').locator('..').getByText('29', { exact: true }),
  ).toBeVisible();
  await expect(
    importPage
      .getByText('Sources with published tasks')
      .locator('..')
      .getByText('3', { exact: true }),
  ).toBeVisible();
  await importPage.getByRole('button', { name: 'Load more records' }).click();
  await expect(importPage.getByText('29 of 29 matching records loaded')).toBeVisible();
  await importPage.getByLabel('Search this view').fill('Synthetic browser pagination case 025');
  await importPage.getByRole('button', { name: 'Search all records' }).click();
  await expect(importPage.getByText('1 of 1 matching records loaded')).toBeVisible();
  await expect(
    importPage.getByRole('heading', { name: 'Synthetic browser pagination case 025', exact: true }),
  ).toBeVisible();
  for (const ctx of Object.values(contexts)) await ctx.close();
});
