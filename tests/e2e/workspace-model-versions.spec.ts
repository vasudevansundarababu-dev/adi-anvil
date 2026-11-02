import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';

test('Admin edits models without manual pricing or terms and disables future selection', async ({
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
  // Seed legacy metadata through the API fixture; the UI must preserve it without fields.
  const legacyPrice = {
    reference: 'Test-only historical rate metadata',
    source_url: 'https://example.test/legacy-rates',
    input_micro_usd_per_million_tokens: 1234567,
    output_micro_usd_per_million_tokens: 7654321,
    expires_at: new Date(Date.now() + 86400000).toISOString(),
  };
  await page.route('**' + base, async (route) => {
    if (route.request().method() !== 'POST') return route.continue();
    const response = await route.fetch({
      postData: JSON.stringify({
        ...route.request().postDataJSON(),
        pricing: legacyPrice,
        processing_terms_reviewed: true,
        processing_terms_reference: 'Test-only historical terms reference',
      }),
    });
    await route.fulfill({ response });
  });
  await page.goto('/workspace/' + project + '/models');
  await page.getByRole('button', { name: 'Add model', exact: true }).click();
  await page.getByLabel('Profile name', { exact: false }).fill(name);
  await page
    .getByRole('region', { name: 'Model configuration editor' })
    .getByLabel('Exact model ID', { exact: false })
    .fill('test-only-model-v1');
  await page
    .getByRole('region', { name: 'Model configuration editor' })
    .getByLabel('Maximum output tokens', { exact: false })
    .fill('2048');
  await expect(page.getByRole('group', { name: 'Saved API key', exact: true })).toContainText(
    'No key selected for this model',
  );
  const initialResponse = page.waitForResponse(
    (r) => r.url().endsWith('/workspace/models') && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Save model profile', exact: true }).click();
  const initial = (await (await initialResponse).json()).data;
  expect(initial.pricing.input_micro_usd_per_million_tokens).toBe(1234567);
  await page.unroute('**' + base);
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
  await expect(
    page
      .getByRole('region', { name: 'Model configuration editor' })
      .getByRole('combobox', { name: 'Provider', exact: true }),
  ).toBeDisabled();
  await page
    .getByRole('region', { name: 'Model configuration editor' })
    .getByLabel('Exact model ID', { exact: false })
    .fill('test-only-model-v2');
  await expect(page.getByText('Pricing and processing terms', { exact: true })).toHaveCount(0);
  await expect(page.getByLabel('Pricing reference', { exact: false })).toHaveCount(0);
  await expect(page.getByLabel('Processing terms reference', { exact: false })).toHaveCount(0);
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
  expect(updated.pricing).toEqual(initial.pricing);
  expect(updated.processing_terms).toEqual(initial.processing_terms);
  await expect(
    page.getByRole('heading', { name: 'Model version history', exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Model version history', exact: true }),
  ).toBeFocused();
  await page.reload();
  await expect(region).toHaveAttribute('aria-busy', 'false');
  const row = await rowForModel();
  await expect(row.getByText('test-only-model-v2', { exact: true })).toBeVisible();
  const old = (await (await page.request.get(base + '/' + initial.id + '/configuration')).json())
    .data;
  expect(old.model_id).toBe('test-only-model-v1');
  expect(old.config_hash).toBe(initial.config_hash);
  expect(old.pricing).toEqual(initial.pricing);
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
