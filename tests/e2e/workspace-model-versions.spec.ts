import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';

test('Admin edits models as immutable versions with explicit pricing and disables future selection', async ({
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
  const base = '/api/v1/projects/' + project + '/workspace/models';
  const name = 'Test-only model version browser ' + Date.now();
  await page.goto('/workspace/' + project + '/models');
  await page.getByRole('button', { name: 'Add model', exact: true }).click();
  await page.getByLabel('Profile name', { exact: false }).fill(name);
  await page.getByLabel('Exact model ID', { exact: false }).fill('test-only-model-v1');
  await page.getByLabel('Maximum output tokens', { exact: false }).fill('2048');
  await expect(page.getByLabel('API key', { exact: true })).toBeDisabled();
  const initialResponse = page.waitForResponse(
    (r) => r.url().endsWith('/workspace/models') && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Save model profile', exact: true }).click();
  const initial = (await (await initialResponse).json()).data;
  expect(initial.pricing).toBeNull();
  const region = page.getByRole('region', { name: 'Model profile list', exact: true });
  await expect(region).toHaveAttribute('aria-busy', 'false');
  async function rowForModel() {
    const row = page.getByRole('row').filter({ hasText: name });
    while (!(await row.count())) {
      const loaded = page.waitForResponse(
        (r) => r.url().includes('/workspace/models?') && new URL(r.url()).searchParams.has('after'),
      );
      await page.getByRole('button', { name: 'Load more profiles', exact: true }).click();
      await loaded;
      await expect(region).toHaveAttribute('aria-busy', 'false');
    }
    return row;
  }
  await (await rowForModel())
    .getByRole('button', { name: 'Edit as new version', exact: true })
    .click();
  await expect(
    page.getByRole('heading', { name: 'Edit model as new version', exact: true }),
  ).toBeVisible();
  await expect(page.getByRole('combobox', { name: 'Provider', exact: true })).toBeDisabled();
  await page.getByLabel('Exact model ID', { exact: false }).fill('test-only-model-v2');
  await page.getByText('Pricing and processing terms', { exact: true }).click();
  await page.getByLabel('Include reviewed pricing metadata', { exact: true }).check();
  await expect(page.getByLabel('Input price', { exact: false })).toHaveValue('');
  await expect(page.getByLabel('Output price', { exact: false })).toHaveValue('');
  await page
    .getByLabel('Pricing reference', { exact: false })
    .fill('Test-only metadata; no real provider rate');
  await page.getByLabel('Pricing source', { exact: false }).fill('https://example.test/pricing');
  await page.getByLabel('Input price', { exact: false }).fill('1.234567');
  await page.getByLabel('Output price', { exact: false }).fill('7.654321');
  const future = new Date(Date.now() + 3 * 86400000);
  await page
    .getByLabel('Pricing expires', { exact: false })
    .fill(
      new Date(future.getTime() - future.getTimezoneOffset() * 60000).toISOString().slice(0, 16),
    );
  await page.getByLabel("I reviewed this provider's processing terms", { exact: true }).check();
  await page
    .getByLabel('Processing terms reference', { exact: false })
    .fill('Test-only terms metadata, not processing rights approval');
  await page.setViewportSize({ width: 320, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.getByRole('region', { name: 'Model configuration editor', exact: true }).screenshot({
    path: 'artifacts/test-runs/modern-model-version-editor.png',
  });
  const versionResponse = page.waitForResponse(
    (r) => r.url().endsWith('/' + initial.id + '/versions') && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Save new model version', exact: true }).click();
  const updatedResponse = await versionResponse;
  expect(updatedResponse.status()).toBe(200);
  const updated = (await updatedResponse.json()).data;
  expect(updated.version).toBe(2);
  expect(updated.profile_id).toBe(initial.profile_id);
  expect(updated.pricing.input_micro_usd_per_million_tokens).toBe(1234567);
  expect(updated.pricing.output_micro_usd_per_million_tokens).toBe(7654321);
  await expect(
    page.getByRole('heading', { name: 'Model version history', exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(region).toHaveAttribute('aria-busy', 'false');
  const row = await rowForModel();
  await expect(row.getByText('test-only-model-v2', { exact: true })).toBeVisible();
  const old = (await (await page.request.get(base + '/' + initial.id + '/configuration')).json())
    .data;
  expect(old.model_id).toBe('test-only-model-v1');
  expect(old.config_hash).toBe(initial.config_hash);
  expect(old.pricing).toBeNull();
  await row.getByRole('button', { name: 'Disable profile', exact: true }).click();
  await expect(
    page.getByText('Profile disabled for new preparations.', { exact: false }),
  ).toBeVisible();
  await expect(region).toHaveAttribute('aria-busy', 'false');
  const disabled = await rowForModel();
  await expect(
    disabled.getByRole('button', { name: 'Edit as new version', exact: true }),
  ).toBeDisabled();
  await expect(disabled).toContainText('Disabled');
});
