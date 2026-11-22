import { test, expect, type Browser, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';

// RL Gym v2 (RLGYM_V2=1) on the local Studio and ADI Forge stubs. Synthetic Golden KYC V8 only; no model is called.
test.skip(process.env.RLGYM_V2 !== '1', 'RL Gym v2 is behind RLGYM_V2=1');

const PROJECT = 'prj_7f3a91c2';

async function signIn(browser: Browser, username: string): Promise<Page> {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto('/gym');
  await page.getByRole('link', { name: 'Sign in with Keycloak' }).click();
  await page.locator('#username').fill(username);
  const password = readFileSync('.local/demo-accounts.md', 'utf8')
    .split('\n')
    .find((l) => l.startsWith('- ' + username + ':'))!
    .split('`')[1];
  await page.locator('#password').fill(password);
  await page.locator('#kc-login').click();
  await expect(
    page.getByRole('link', { name: 'ADI Labs Forge · RL Gym Evaluation home' }),
  ).toBeVisible();
  return page;
}

test.beforeAll(async ({ request }) => {
  // Studio releases Golden KYC V8 and ADI Forge exports KYC November (idempotent stub controls).
  const studio = await request.post('http://127.0.0.1:8211/stub/bootstrap', { timeout: 240000 });
  expect(studio.ok()).toBeTruthy();
  const forge = await request.post(`http://127.0.0.1:8212/stub/projects/${PROJECT}/export`, {
    data: {},
  });
  expect([200, 201]).toContain((await forge.json()).status);
});

test('entry, projects, project page, tasks and exports', async ({ browser }) => {
  const page = await signIn(browser, 'researcher');
  await expect(page).toHaveURL(/\/gym$/);
  for (const menu of ['Home', 'Projects', 'Runs', 'Admin']) {
    await expect(page.getByRole('link', { name: menu, exact: true })).toBeVisible();
  }
  await expect(page.getByRole('heading', { name: 'Leaderboard' })).toBeVisible();
  // Empty until a run completes; afterwards the latest completed run's cohort is ranked.
  await expect(
    page
      .getByText('No completed benchmark results for this Project.')
      .or(page.getByRole('cell', { name: '1', exact: true })),
  ).toBeVisible();
  await page.getByRole('link', { name: 'Projects', exact: true }).click();
  const row = page.getByRole('row', { name: /KYC November/ });
  await expect(row).toContainText('Project ID prj_7f3a91c2');
  await expect(row).toContainText('Golden KYC V8');
  await expect(row).toContainText('Template ID tpl_kyc_01');
  await expect(row).toContainText('kyc · golden-kyc-openenv v3 · Qualified');
  await expect(row).toContainText('40 tasks');
  await expect(row).toContainText('Ready');
  await row.getByRole('link', { name: 'KYC November' }).click();
  await expect(page.getByRole('heading', { name: 'KYC November' })).toBeVisible();
  await expect(page.getByRole('row', { name: /task-kyc-0001 · r1/ })).toBeVisible();
  await page.getByRole('link', { name: /task-kyc-0013 · r1/ }).click();
  await expect(page.getByText('As the agent sees it')).toBeVisible();
  await expect(page.getByText('Reviewer only · view audited')).toBeVisible();
  await page.goto(`/gym/projects/${PROJECT}/exports`);
  await expect(page.getByRole('row', { name: /exp-0001/ })).toContainText(
    '40 new · 0 superseding · 0 unchanged · 0 blocked',
  );
  await page.screenshot({ path: 'artifacts/test-runs/rlgym-v2-exports.png', fullPage: true });
  // To do: export received and project ready to run, opened by events.
  // "Ready to run" closes when the project's first run is admitted (run.admitted), so it shows only before any run.
  const runs = await page.request.get(
    `/api/v1/workspaces/adi-labs-research/runs?project=${PROJECT}`,
  );
  const neverRun = ((await runs.json()).data.items as { state: string }[]).every(
    (r) => r.state === 'refused',
  );
  await page.getByRole('button', { name: /To do/ }).click();
  const novemberReady = page
    .getByRole('dialog', { name: 'To do' })
    .getByText(/^KYC November\d* ?\d+ ready tasks/);
  if (neverRun) {
    await expect(page.getByRole('dialog', { name: 'To do' })).toContainText('Ready to run');
  } else {
    await expect(novemberReady).toHaveCount(0);
  }
  await expect(page.getByRole('dialog', { name: 'To do' })).toContainText('Import / Export');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog', { name: 'To do' })).toHaveCount(0);
});

test('override needs a second binding approver', async ({ browser }) => {
  const researcher = await signIn(browser, 'researcher');
  await researcher.goto(`/gym/projects/${PROJECT}/selection-rules`);
  await expect(
    researcher.getByText('Would bind now: golden-kyc-openenv v3 · Qualified'),
  ).toBeVisible();
  await expect(researcher.getByText('20 criteria', { exact: false })).toBeVisible();
  const rule = researcher.getByLabel('New rule');
  const pinV2 = await rule
    .locator('option', { hasText: 'Pinned · golden-kyc-openenv v2' })
    .getAttribute('value');
  await rule.selectOption(pinV2!);
  await researcher.getByLabel('Reason').fill('Finish a comparison on v2 before moving (e2e)');
  await researcher.getByRole('button', { name: 'Request override' }).click();
  await expect(researcher.getByText(/Override ov-\d+ requested/)).toBeVisible();
  await researcher.getByRole('link', { name: 'Review' }).first().click();
  const panel = researcher.getByRole('dialog', { name: /Review override/ });
  await expect(panel).toContainText('the requester cannot decide');
  await expect(panel.getByRole('button', { name: 'Approve' })).toBeDisabled();
  await researcher.screenshot({
    path: 'artifacts/test-runs/rlgym-v2-review-requester.png',
    fullPage: true,
  });

  const approver = await signIn(browser, 'admin-1');
  await approver.getByRole('button', { name: /To do/ }).click();
  await expect(approver.getByRole('dialog', { name: 'To do' })).toContainText(
    'Override waiting for approval',
  );
  await approver.getByRole('link', { name: 'Approve or reject' }).first().click();
  const review = approver.getByRole('dialog', { name: /Review override/ });
  await expect(review).toContainText('Same seed family');
  await review.getByRole('button', { name: 'Approve' }).click();
  await expect(approver.getByText('Rule: Pinned · golden-kyc-openenv v2')).toBeVisible();
  await expect(approver.getByText('template rule: Same data · kyc_cases-20261119')).toBeVisible();
  await approver.getByRole('button', { name: 'Remove override' }).click();
  await expect(approver.getByText('Rule: Same data · kyc_cases-20261119')).toBeVisible();
  await expect(
    approver.getByText('Would bind now: golden-kyc-openenv v3 · Qualified'),
  ).toBeVisible();
});

test('admin environments, evaluators and templates', async ({ browser }) => {
  const page = await signIn(browser, 'admin-2');
  await page.goto('/gym/admin/environments');
  await expect(
    page.getByRole('row', { name: /golden-kyc-openenv Studio release rel-0431/ }),
  ).toContainText('400 cases');
  await expect(page.getByRole('row', { name: /golden-kyc-openenv.*v2/ })).toContainText('20 cases');
  await page.goto('/gym/admin/environments/golden-kyc-openenv@v3');
  await expect(page.getByText('state_cleared')).toBeVisible();
  await expect(page.getByText('Dataset kyc_cases', { exact: false })).toBeVisible();
  await page.goto('/gym/admin/evaluators');
  await expect(page.getByRole('row', { name: /golden-kyc:screening · v1/ })).toContainText(
    'Qualified',
  );
  await expect(page.getByRole('row', { name: /golden-kyc:screening · v1/ })).toContainText(
    'allowed ✓',
  );
  await page.getByRole('link', { name: 'golden-kyc:screening · v1' }).click();
  await expect(page.getByText('Studio S7 binding', { exact: false })).toBeVisible();
  await page.goto('/gym/admin/templates');
  await expect(page.getByRole('row', { name: /Golden KYC V8/ })).toContainText('Active');
  await page.getByRole('link', { name: 'Golden KYC V8' }).click();
  await expect(page.getByText('Known-case tests passed (20 of 20)')).toBeVisible();
  await page.screenshot({ path: 'artifacts/test-runs/rlgym-v2-template.png', fullPage: true });
});

test('outsider is not in the workspace', async ({ browser }) => {
  const page = await signIn(browser, 'outsider');
  await expect(page.getByText('Workspace isolation-control', { exact: false })).toBeVisible();
  const res = await page.request.get('/api/v1/workspaces/adi-labs-research/projects');
  expect(res.status()).toBe(403);
  expect((await res.json()).error.code).toBe('TENANT_SCOPE_VIOLATION');
});

test('models, model sets and keys use the controlled mock locally', async ({ browser }) => {
  const page = await signIn(browser, 'admin-1');
  await page.getByRole('link', { name: 'Admin', exact: true }).click();
  const row = page.getByRole('row', { name: /Mock agent · diligent/ });
  await expect(row).toContainText('Controlled mock (local)');
  await row.getByRole('button', { name: 'Test now' }).click();
  await expect(page.getByText(/Mock agent · diligent \(synthetic\) v1: ok/)).toBeVisible();
  await expect(page.getByRole('row', { name: /Mock agent · diligent/ })).toContainText('Ready');
  await page.getByRole('link', { name: 'Model sets' }).click();
  await expect(page.getByRole('row', { name: /KYC line-up \(mock\)/ })).toContainText(
    'Mock agent · erratic (synthetic) v1',
  );
  await page.getByRole('link', { name: 'Keys', exact: true }).click();
  await expect(page.getByRole('row', { name: /Controlled mock/ })).toContainText('••••mock');
  await page.screenshot({ path: 'artifacts/test-runs/rlgym-v2-keys.png', fullPage: true });
});

test('short data plan: lower one cell, send more data to Studio, save the suite', async ({
  browser,
}) => {
  const page = await signIn(browser, 'researcher');
  await page.goto(`/gym/projects/${PROJECT}/suites`);
  await expect(page.getByRole('row', { name: /KYC November default/ })).toContainText('v1');
  await page
    .getByRole('button', { name: /New suite version|Open draft/ })
    .first()
    .click();
  await expect(page.getByRole('heading', { name: 'Can this suite run?' })).toBeVisible();
  await page.getByRole('link', { name: '2 Data plan' }).click();
  await page.getByLabel('Sample size (cases per run, per model and attempt)').fill('400');
  await page.getByLabel('minor_without_tin').fill('40');
  // A fresh sampling seed makes this suite version new on every run, so the test can repeat on the same database.
  await page.getByLabel('Sampling seed').fill(String(Date.now() % 1000000000));
  await page.getByRole('button', { name: 'Apply data plan' }).click();
  await expect(page.getByText('the plan asks for 40; the data has 33')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Save suite version' })).toBeDisabled();
  await page.getByRole('button', { name: 'Lower to what exists' }).first().click();
  await page.getByRole('button', { name: 'Send to Studio inbox (more data)' }).click();
  const form = page.getByRole('dialog', { name: 'Send to Studio inbox (more data)' });
  for (const box of await form.locator('textarea').all()) {
    await box.fill('More synthetic applications of this kind, same rules, varied states (e2e)');
  }
  await form.getByRole('button', { name: 'Send to Studio inbox' }).click();
  await expect(page.getByText(/More-data item .* queued/)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Save suite version' })).toBeEnabled();
  await page.screenshot({ path: 'artifacts/test-runs/rlgym-v2-suite-short.png', fullPage: true });
  await page.getByRole('button', { name: 'Save suite version' }).click();
  await expect(page.getByText(/Saved as kyc-november-default-v\d+/)).toBeVisible();
  await page.getByRole('button', { name: /To do/ }).click();
  await expect(page.getByRole('dialog', { name: 'To do' })).toContainText('Studio inbox');
});

test('new run: admission checklist, start, episodes run in the local container, scores', async ({
  browser,
}) => {
  test.setTimeout(420000);
  const page = await signIn(browser, 'researcher');
  await page.goto(`/gym/runs/new?project=${PROJECT}`);
  await expect(page.getByRole('heading', { name: 'Admission checklist' })).toBeVisible();
  await page.getByLabel('Suite').selectOption({ label: 'KYC November default · v1' });
  await page.getByLabel('Budget cap (USD)').fill('0.5');
  await expect(page.getByText(/BUDGET_EXCEEDED: projected \$1\.2/)).toBeVisible();
  await page.getByLabel('Budget cap (USD)').fill('5');
  await expect(page.getByText('Passed', { exact: true })).toBeVisible({ timeout: 30000 });
  await expect(page.getByText(/120 episodes · projected/)).toBeVisible();
  await expect(page.getByText(/not model performance/).first()).toBeVisible();
  await page.screenshot({ path: 'artifacts/test-runs/rlgym-v2-new-run.png', fullPage: true });
  await page.getByRole('button', { name: 'Start run' }).click();
  await expect(page).toHaveURL(/\/gym\/runs\/run-\d{4}$/);
  await expect(page.getByRole('heading', { name: /Completed/ })).toBeVisible({ timeout: 360000 });
  await expect(page.getByText('What this run used')).toBeVisible();
  await expect(page.getByText(/golden-kyc-openenv v3 · Follow project rules/)).toBeVisible();
  await expect(page.getByText(/rlgym-local\/golden-kyc-openenv:v3-/)).toBeVisible();
  await expect(page.getByText(/Scored 120/)).toBeVisible();
  await page.screenshot({ path: 'artifacts/test-runs/rlgym-v2-run-overview.png', fullPage: true });
  await page.getByRole('link', { name: 'Episodes', exact: true }).click();
  await expect(page.getByText('120 episodes · page 1')).toBeVisible();
  await page.getByLabel('Verdict').selectOption('failed');
  await expect(page.getByText(/episodes · page 1/)).toBeVisible();
  await page.getByRole('link', { name: 'Report', exact: true }).click();
  await expect(page.getByRole('navigation', { name: 'Report views' })).toBeVisible();
  await page.goto('/gym/runs?state=completed');
  await expect(page.getByRole('row', { name: /KYC November/ }).first()).toContainText('Completed');
});

test('a viewer sees runs but cannot start one', async ({ browser }) => {
  const page = await signIn(browser, 'sales');
  await page.goto(`/gym/runs/new?project=${PROJECT}`);
  await expect(page.getByText('Viewers cannot start runs.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Start run' })).toBeDisabled();
});

test('report: five views, drill-downs, diagnosis and PDF export', async ({ browser }) => {
  test.setTimeout(240000);
  const page = await signIn(browser, 'researcher');
  const runs = await page.request.get('/api/v1/workspaces/adi-labs-research/runs?state=completed');
  const run = ((await runs.json()).data.items as { id: string }[])[0];
  test.skip(!run, 'needs a completed run (the new-run test makes one)');
  await page.goto('/gym/runs?state=completed');
  await page
    .getByRole('row', { name: new RegExp(run.id) })
    .getByRole('link', { name: 'Report' })
    .click();
  await expect(page).toHaveURL(new RegExp(`/gym/runs/${run.id}/report$`));
  await expect(page.getByText(/Matched cohort: \d+ cases/)).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Capability profile' })).toBeVisible();
  await expect(page.getByText('PASSED').first()).toBeVisible();
  await page.screenshot({
    path: 'artifacts/test-runs/rlgym-v2-report-overview.png',
    fullPage: true,
  });
  for (const view of [
    'Task results',
    'Agent performance',
    'Failures & evidence',
    'Trust & Safety',
  ]) {
    await page
      .getByRole('navigation', { name: 'Report views' })
      .getByRole('link', { name: view })
      .click();
    await expect(page.getByRole('link', { name: view, exact: true })).toHaveAttribute(
      'aria-current',
      'page',
    );
  }
  await expect(
    page.getByText(/Trust & Safety was off for this run|approved attack prompts/),
  ).toBeVisible();
  await page.getByRole('link', { name: 'Failures & evidence' }).click();
  await expect(page.getByRole('heading', { name: 'Failures by likely cause' })).toBeVisible();
  await page.screenshot({
    path: 'artifacts/test-runs/rlgym-v2-report-failures.png',
    fullPage: true,
  });
  await page.getByRole('link', { name: 'Diagnose' }).first().click();
  await expect(
    page.getByRole('heading', { name: 'Stage 1 · Sealed automated score' }),
  ).toBeVisible();
  await page.getByLabel('Attributed to').selectOption('agent');
  await page.getByLabel('Strength of evidence').selectOption('strong');
  await page.getByLabel('K3 Agent output and state').check();
  await page
    .getByLabel('Why this evidence supports the finding')
    .fill('The agent skipped a required check (e2e).');
  await page.getByRole('button', { name: 'Save diagnosis' }).click();
  await expect(page.getByRole('button', { name: 'Saved' })).toBeVisible();
  await page.getByRole('link', { name: 'Report', exact: true }).first().click();
  await page.getByRole('link', { name: 'Risk & escalation summary' }).click();
  await expect(page.getByRole('cell', { name: /Possible screening match/ })).toBeVisible();
  await page.goto(`/gym/runs/${run.id}/report`);
  await page.getByRole('link', { name: 'Export PDF' }).click();
  await expect(page.getByRole('heading', { name: /PDF preview · \d+ pages \(A4\)/ })).toBeVisible({
    timeout: 60000,
  });
  await expect(page.locator('iframe.pdf')).toBeVisible();
  const download = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Download PDF' }).click();
  expect((await download).suggestedFilename()).toMatch(new RegExp(`report-${run.id}-r\\d+\\.pdf`));
  await page.screenshot({ path: 'artifacts/test-runs/rlgym-v2-report-pdf.png', fullPage: true });
});

test('episode viewer and SME review through the ADI Forge stub', async ({ browser }) => {
  test.setTimeout(240000);
  const page = await signIn(browser, 'researcher');
  const runs = await page.request.get('/api/v1/workspaces/adi-labs-research/runs?state=completed');
  const run = ((await runs.json()).data.items as { id: string; project_id: string }[]).find(
    (r) => r.project_id === PROJECT,
  );
  test.skip(!run, 'needs a completed KYC November run (the new-run test makes one)');
  await page.goto(`/gym/runs/${run!.id}/episodes`);
  await page.getByRole('link', { name: new RegExp(`${run!.id}-e0001`) }).click();
  await expect(page.getByRole('heading', { name: 'Path taken' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Timeline' })).toBeVisible();
  await page.getByRole('button', { name: /^screening/ }).click();
  await expect(page.getByText('golden-kyc:screening v')).toBeVisible();
  await page.screenshot({
    path: 'artifacts/test-runs/rlgym-v2-episode-viewer.png',
    fullPage: true,
  });
  await page.goto(`/gym/runs/${run!.id}/sme`);
  await page.getByLabel('Failed only').uncheck();
  const boxes = page.getByRole('checkbox', { name: /^Include / });
  await boxes.nth(0).check();
  await boxes.nth(1).check();
  await page.getByRole('button', { name: 'Send 2 to SME review' }).click();
  await expect(page.getByText(/Batch smr-\d+ · 2 items/).first()).toBeVisible();
  await expect(page.getByText(/Authoring rr-\d+/).first()).toBeVisible({ timeout: 30000 });
  const view = await page.request.get(
    `/api/v1/workspaces/adi-labs-research/runs/${run!.id}/sme-review`,
  );
  const batch = (await view.json()).data.batches[0];
  const decide = await page.request.post(
    `http://127.0.0.1:8212/stub/projects/${PROJECT}/sme-decisions/${batch.id}`,
    {
      data: {
        decisions: batch.items.map((i: { id: string }, n: number) => ({
          item_id: i.id,
          decision: n === 0 ? 'agent_failure' : 'environment_wrong',
          rationale: 'Decided in the ADI Forge stub (e2e)',
          decided_by: 'SME (ADI Forge stub)',
        })),
      },
    },
  );
  expect((await decide.json()).status).toBe(200);
  await page.reload();
  await expect(page.getByText('Agent failure confirmed').first()).toBeVisible();
  await expect(page.getByText(/automated → reviewed/).first()).toBeVisible();
  await page.screenshot({ path: 'artifacts/test-runs/rlgym-v2-sme-review.png', fullPage: true });
  await page.goto(`/gym/runs/${run!.id}/report`);
  await expect(page.getByText(/2 of 2 decided by SMEs in Authoring/)).toBeVisible();
});

test('leaderboard ranks the latest cohort and an admin invites and removes a viewer', async ({
  browser,
}) => {
  const page = await signIn(browser, 'admin-1');
  await page.goto(`/gym?project=${PROJECT}`);
  await expect(page.getByRole('heading', { name: 'Leaderboard' })).toBeVisible();
  const first = page.getByRole('row').nth(1);
  await expect(first).toContainText('Mock agent · diligent');
  await expect(first).toContainText('PASSED');
  await expect(page.getByLabel('Cohort')).toBeVisible();
  await page.screenshot({ path: 'artifacts/test-runs/rlgym-v2-leaderboard.png', fullPage: true });
  await page.goto('/gym/admin/users');
  await page.getByRole('button', { name: 'Invite user' }).click();
  const dialog = page.getByRole('dialog', { name: 'Invite user' });
  const username = `e2e-${Date.now().toString(36)}`;
  await dialog.getByLabel('Username').fill(username);
  await dialog.getByLabel('Email').fill(`${username}@anvil.invalid`);
  await dialog.getByLabel('Full name').fill('E2E Invitee');
  await dialog.getByRole('button', { name: 'Invite', exact: true }).click();
  await expect(dialog.getByText('Temporary password:')).toBeVisible();
  await dialog.getByRole('button', { name: 'Done' }).click();
  const row = page.getByRole('row', { name: new RegExp(`${username}@anvil.invalid`) });
  await expect(row).toContainText('Viewer');
  page.once('dialog', (d) => d.accept());
  await row.getByRole('button', { name: 'Remove access' }).click();
  await expect(row).toContainText('removed');
});
