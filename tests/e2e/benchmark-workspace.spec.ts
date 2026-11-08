import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';

test('real OIDC benchmark intake persists a quarantined fictional receipt without execution', async ({
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
  await page.goto('/workspace/' + project + '/benchmarks');
  await expect(page.getByRole('heading', { name: 'Import from Praxis' })).toBeVisible();
  await expect(
    page.getByText('Paid candidate and judge calls remain disabled.', { exact: false }),
  ).toBeVisible();
  await expect(page.getByRole('complementary', { name: 'UI mockup disclosure' })).toHaveCount(0);
  await page
    .getByLabel('Praxis export archive')
    .setInputFiles('.local/testing-unsigned-bundle.tar.gz');
  const imported = page.waitForResponse(
    (r) => r.url().endsWith('/workspace/benchmarks/imports') && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Validate and import' }).click();
  const response = await imported;
  expect(response.status()).toBe(200);
  expect(response.request().headers()['content-type']).toBe('application/gzip');
  expect(response.request().headers()['x-csrf-token']).toBeTruthy();
  expect(response.request().headers()['idempotency-key']).toBeTruthy();
  // A router transition may evict Chrome's POST body cache; fetch the persisted
  // receipt through the authenticated API rather than depend on inspector cache.
  await expect(page).toHaveURL(/receipt=[a-f0-9-]+/);
  const receiptId = new URL(page.url()).searchParams.get('receipt');
  const stored = await page.request.get(
    '/api/v1/projects/' + project + '/workspace/benchmarks/imports/' + receiptId,
  );
  expect(stored.status()).toBe(200);
  const receipt = (await stored.json()).data;
  expect(receipt.source_state).toBe('quarantined');
  expect(receipt.signature_status).toBe('unsigned');
  expect(receipt.task_count).toBe(3);
  await expect(page).toHaveURL(new RegExp('receipt=' + receipt.receipt_id));
  const detail = page.getByRole('region', { name: 'Source and qualification' });
  await expect(detail).toContainText('signature unsigned');
  await expect(detail).toContainText('quarantined');
  await expect(page.getByRole('button', { name: 'Build reviewed source' })).toBeDisabled();
  await page.reload();
  await expect(page.getByRole('region', { name: 'Source and qualification' })).toContainText(
    'quarantined',
  );
  await expect(page.getByRole('heading', { name: 'Comparison matrix' })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Results and evidence' })).toHaveCount(0);
  await page.screenshot({ path: 'artifacts/test-runs/benchmark-workspace.png', fullPage: true });
  const foreign = await page.request.get(
    '/api/v1/projects/a0000000-0000-4000-8000-000000000003/workspace/benchmarks/imports/' +
      receipt.receipt_id,
  );
  expect([403, 404]).toContain(foreign.status());
});
