import { test, expect, BrowserContext } from '@playwright/test';
import { readFileSync } from 'node:fs';

test('provider preparation has no expired pricing or spending defaults', async ({ browser }) => {
  const context = await browser.newContext();
  const page = await login(context, 'admin-1');
  await page.goto('/p/a0000000-0000-4000-8000-000000000002/providers');
  await page.locator('details:has(#openai-pricing) > summary').click();
  await expect(page.locator('#openai-pricing')).toHaveValue('');
  await expect(page.locator('#openai-bound')).toHaveValue('');
  await expect(
    page.getByText('Historical marketing pricing expired', { exact: false }),
  ).toBeVisible();
  const health = await (await page.request.get('/api/v1/health')).json();
  expect(health.data.harbor_live_dispatch).toBe('disabled');
  await context.close();
});

async function login(context: BrowserContext, name: string) {
  const page = await context.newPage();
  await page.goto('/');
  await page.getByRole('link', { name: 'Sign in with Keycloak' }).click();
  await page.locator('#username').fill(name);
  const password = readFileSync('.local/demo-accounts.md', 'utf8')
    .split('\n')
    .find((l) => l.startsWith('- ' + name + ':'))!
    .split('`')[1];
  await page.locator('#password').fill(password);
  await page.locator('#kc-login').click();
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible();
  return page;
}

test('modern package build shows progress, retry, saved feedback and the next step', async ({
  browser,
}) => {
  const context = await browser.newContext();
  const page = await login(context, 'admin-1');
  const project = 'a0000000-0000-4000-8000-000000000002';
  await page.goto('/workspace/' + project + '/tasks');
  await page.getByRole('button', { name: 'Import / prepare run', exact: true }).click();
  const fixture = JSON.parse(
    readFileSync('contracts/praxis/synthetic-marketing.task.json', 'utf8'),
  );
  fixture.task_id += '-build-feedback-' + Date.now();
  await page.getByLabel('Praxis task export (.json)').setInputFiles({
    name: 'synthetic-build-feedback.json',
    mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify(fixture)),
  });
  const buildPath = '**/praxis-sources/*/build';
  await page.route(buildPath, (route) =>
    route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({ error: { message: 'Test-only package build interruption' } }),
    }),
  );
  await page.getByRole('button', { name: 'Build Harbor package', exact: true }).click();
  await expect(
    page.getByRole('alert').filter({ hasText: 'Test-only package build interruption' }),
  ).toBeVisible();
  await page.unroute(buildPath);
  let releaseBuild!: () => void;
  const gate = new Promise<void>((resolve) => {
    releaseBuild = resolve;
  });
  await page.route(buildPath, async (route) => {
    await gate;
    await route.continue();
  });
  const response = page.waitForResponse(
    (r) => r.url().endsWith('/build') && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Build Harbor package', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Building Harbor package…', exact: true }),
  ).toBeDisabled();
  await expect(page.getByLabel('Imported revision', { exact: true })).toBeDisabled();
  releaseBuild();
  const built = await response;
  expect(built.status()).toBe(200);
  const first = (await built.json()).data;
  await expect(
    page.getByRole('heading', { name: 'Harbor package ready', exact: true }),
  ).toBeFocused();
  await expect(
    page.getByRole('status').filter({ hasText: 'Harbor package is ready.' }),
  ).toBeVisible();
  await expect(page.getByText('Test-only package build interruption', { exact: true })).toHaveCount(
    0,
  );
  await page.unroute(buildPath);
  const repeated = page.waitForResponse(
    (r) => r.url().endsWith('/build') && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Build Harbor package', exact: true }).click();
  expect((await (await repeated).json()).data.id).toBe(first.id);
  await expect(
    page.getByRole('heading', { name: 'Harbor package ready', exact: true }),
  ).toBeFocused();
  await page.getByRole('link', { name: 'Run', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Create execution group', exact: true }),
  ).toBeVisible();
  await expect(page.locator('#preparation-package')).toHaveValue(first.id);
  await expect(page.getByLabel('Aggregate API budget', { exact: false })).toHaveValue('');
  await context.close();
});

test('Praxis export to staged Harbor check with real OIDC and retained analysis', async ({
  browser,
}) => {
  const researcherContext = await browser.newContext();
  const ownerContext = await browser.newContext();
  const researcher = await login(researcherContext, 'researcher');
  const path = '/p/a0000000-0000-4000-8000-000000000002/harbor';
  await researcher.goto(path);
  const fixture = JSON.parse(
    readFileSync('contracts/praxis/synthetic-marketing-staged.task.json', 'utf8'),
  );
  fixture.task_id += '-browser-' + Date.now();
  await researcher.getByLabel('Praxis task export (.json)').setInputFiles({
    name: 'praxis-staged.json',
    mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify(fixture)),
  });
  await expect(
    researcher.getByRole('button', { name: 'Build Harbor package', exact: true }),
  ).toBeVisible();
  await researcher.getByText('Inspect actor-visible task', { exact: true }).click();
  await expect(researcher.getByText('FUTURE-NORTHSTAR', { exact: false })).toHaveCount(0);
  await researcher.getByRole('button', { name: 'Build Harbor package', exact: true }).click();
  await expect(researcher.getByText('Inspect package manifest', { exact: true })).toBeVisible();
  await expect(
    researcher.getByRole('button', { name: 'Run reference check', exact: true }),
  ).toHaveCount(0);
  const owner = await login(ownerContext, 'admin-1');
  await owner.goto(path);
  await expect(owner.getByLabel('Imported revision', { exact: true })).toBeVisible();
  await expect(owner.getByLabel('Imported revision', { exact: true })).toContainText(
    fixture.task_id,
  );
  const sourceValue = await owner
    .getByLabel('Imported revision', { exact: true })
    .locator('option')
    .filter({ hasText: fixture.task_id })
    .getAttribute('value');
  await owner
    .getByLabel('Imported revision', { exact: true })
    .selectOption(sourceValue!, { timeout: 10000 });
  await owner.getByRole('button', { name: 'Run reference check', exact: true }).click();
  await expect(owner.getByRole('heading', { name: 'Check: succeeded', exact: true })).toBeVisible({
    timeout: 60000,
  });
  await expect(owner.getByLabel('Software check analysis')).toContainText('Reward: 1');
  await expect(owner.getByLabel('Software check analysis')).toContainText('stage-revise');
  await owner.reload();
  await owner
    .getByLabel('Imported revision', { exact: true })
    .selectOption(sourceValue!, { timeout: 10000 });
  await expect(owner.getByRole('heading', { name: 'Check: succeeded', exact: true })).toBeVisible();
  await owner.getByRole('button', { name: 'Run hard-failure check', exact: true }).click();
  await expect(owner.getByLabel('Software check analysis')).toContainText('Reward: 0', {
    timeout: 60000,
  });
  await expect(owner.getByLabel('Software check analysis')).toContainText('s2-rule-budget');
  await expect(owner.getByLabel('Check history')).toContainText('succeeded');
  await owner.screenshot({ path: 'artifacts/test-runs/harbor-workbench.png', fullPage: true });
  await researcherContext.close();
  await ownerContext.close();
});
