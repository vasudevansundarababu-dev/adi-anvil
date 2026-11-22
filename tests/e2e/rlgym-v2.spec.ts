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
  await expect(page.getByRole('heading', { name: 'RL Gym', exact: true })).toBeVisible();
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
  await expect(page.getByText('No completed benchmark results for this Project.')).toBeVisible();
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
  await page.getByRole('button', { name: /To do/ }).click();
  await expect(page.getByRole('dialog', { name: 'To do' })).toContainText('Ready to run');
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
  await expect(page.getByRole('row', { name: /golden-kyc-openenv.*v3/ })).toContainText(
    '400 cases',
  );
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
