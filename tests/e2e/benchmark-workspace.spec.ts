import { test, expect, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';

async function signIn(page: Page) {
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
}

test('real OIDC benchmark intake persists a quarantined fictional receipt without execution', async ({
  page,
}) => {
  await signIn(page);
  const project = 'a0000000-0000-4000-8000-000000000002';
  await page.goto('/workspace/' + project + '/benchmarks/setup');
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

test('actual build retries retain their token across reload and isolate changed bodies/projects', async ({
  page,
}) => {
  await signIn(page);
  const project = 'a0000000-0000-4000-8000-000000000002';
  const secondProject = JSON.parse(
    readFileSync('.local/testing-second-project.json', 'utf8'),
  ).project_id;
  const review = '11111111-1111-4111-8111-111111111111';
  const changedReview = '22222222-2222-4222-8222-222222222222';
  async function imported(target: string) {
    await page.goto('/workspace/' + target + '/benchmarks/setup');
    await page
      .getByLabel('Praxis export archive')
      .setInputFiles('.local/testing-unsigned-bundle.tar.gz');
    await page.getByRole('button', { name: 'Validate and import' }).click();
    await expect(page).toHaveURL(/receipt=[a-f0-9-]+/);
    await expect(page.getByRole('region', { name: 'Source and qualification' })).toContainText(
      'quarantined',
    );
  }
  await imported(project);
  const keys: string[] = [];
  await page.route('**/workspace/benchmarks/imports/*/build', async (route) => {
    keys.push(route.request().headers()['idempotency-key']);
    if (keys.length === 1) await route.abort('failed');
    else await route.continue();
  });
  await page.getByLabel('Current source-rights review reference').fill(review);
  await page.getByRole('button', { name: 'Build reviewed source' }).click();
  await expect(page.getByRole('alert')).toBeVisible();
  await expect.poll(() => keys.length).toBe(1);
  expect(keys[0]).toBeTruthy();
  await page.reload();
  await page.getByLabel('Current source-rights review reference').fill(review);
  const replay = page.waitForResponse(
    (r) => r.url().endsWith('/build') && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Build reviewed source' }).click();
  expect([403, 404, 409]).toContain((await replay).status());
  expect(keys[1]).toBe(keys[0]);
  await page.getByLabel('Current source-rights review reference').fill(changedReview);
  const changed = page.waitForResponse(
    (r) => r.url().endsWith('/build') && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Build reviewed source' }).click();
  expect([403, 404, 409]).toContain((await changed).status());
  expect(keys[2]).not.toBe(keys[1]);
  await imported(secondProject);
  await page.getByLabel('Current source-rights review reference').fill(review);
  const foreign = page.waitForResponse(
    (r) => r.url().endsWith('/build') && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Build reviewed source' }).click();
  expect([403, 404, 409]).toContain((await foreign).status());
  expect(keys[3]).not.toBe(keys[0]);
  expect(new Set(keys).size).toBe(3);
  const entries = await page.evaluate(() =>
    Object.entries(sessionStorage).filter(([key]) => key.startsWith('anvil:benchmark:request:')),
  );
  expect(entries.length).toBeGreaterThanOrEqual(3);
  expect(
    entries.every(
      ([key, token]) =>
        /^anvil:benchmark:request:[a-f0-9]{64}$/.test(key) && /^[a-f0-9-]{36}$/.test(token),
    ),
  ).toBe(true);
  expect(JSON.stringify(entries)).not.toContain(review);
  expect(JSON.stringify(entries)).not.toContain(changedReview);
  await expect(page.getByRole('heading', { name: 'Comparison matrix' })).toHaveCount(0);
});
