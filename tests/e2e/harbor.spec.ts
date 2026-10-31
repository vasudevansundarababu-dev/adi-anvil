import { test, expect, BrowserContext } from '@playwright/test';
import { readFileSync } from 'node:fs';

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
  const owner = await login(ownerContext, 'product-owner');
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
  await owner
    .getByLabel('Product Owner rationale')
    .fill(
      'Automated browser software-check approval by a test identity. No human rights clearance.',
    );
  await owner
    .getByRole('button', { name: 'Approve synthetic software checks', exact: true })
    .click();
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
