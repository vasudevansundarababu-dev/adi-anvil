import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';

test('all three golden exports import without exposing private oracles or claiming runnable readiness', async ({
  page,
}) => {
  await page.goto('/');
  await page.getByRole('link', { name: 'Sign in with Keycloak' }).click();
  await page.locator('#username').fill('admin-1');
  const password = readFileSync('.local/demo-accounts.md', 'utf8')
    .split('\n')
    .find((line) => line.startsWith('- admin-1:'))!
    .split('`')[1];
  await page.locator('#password').fill(password);
  await page.locator('#kc-login').click();
  await expect(page.getByRole('button', { name: 'Sign out', exact: true })).toBeVisible();
  const project = 'a0000000-0000-4000-8000-000000000002';
  for (const file of [
    '01-marketing.export.json',
    '02-kyc_aml.export.json',
    '03-fraud.export.json',
  ]) {
    const path = 'contracts/praxis/golden-v3/' + file;
    const payload = JSON.parse(JSON.parse(readFileSync(path, 'utf8')).payload_json);
    await page.goto('/workspace/' + project + '/tasks/import');
    const saved = page.waitForResponse(
      (r) => r.url().endsWith('/praxis-sources') && r.request().method() === 'POST',
    );
    await page.getByLabel('Praxis task export (.json)', { exact: false }).setInputFiles(path);
    const response = await saved;
    expect(response.status()).toBe(200);
    const value = (await response.json()).data;
    expect(value.executable_import.ready).toBe(false);
    await expect(
      page.getByRole('heading', { name: 'Executable source validated', exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole('button', { name: 'Build Harbor package', exact: true }),
    ).toHaveCount(0);
    await expect(page.getByLabel('Environment folder', { exact: true })).toHaveCount(0);
    expect(await page.locator('main').innerText()).not.toContain(payload.evaluation_private.canary);
    await page.getByRole('link', { name: 'View imported task', exact: true }).click();
    await expect(page.getByRole('heading', { name: payload.title, exact: true })).toBeVisible();
    await expect(page.getByText('anvil-golden-tools:1.0.0', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Rubrics', exact: true }).click();
    expect(await page.locator('main').innerText()).not.toContain(payload.evaluation_private.canary);
    await page.getByRole('link', { name: 'Run task', exact: false }).click();
    await expect(
      page.getByRole('heading', {
        name: 'Executable generation is not available yet',
        exact: true,
      }),
    ).toBeVisible();
    await expect(page.getByRole('button', { name: 'Run', exact: true })).toHaveCount(0);
  }
});
