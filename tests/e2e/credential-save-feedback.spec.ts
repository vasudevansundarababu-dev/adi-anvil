import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';

test('a lost credential-save response shows focused feedback and safely confirms the same saved key on retry', async ({
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
  const headers: string[] = [];
  const ids: string[] = [];
  await page.route('**/workspace/credentials', async (route) => {
    if (route.request().method() !== 'POST') return route.continue();
    headers.push(route.request().headers()['idempotency-key']);
    const response = await route.fetch();
    expect(response.status()).toBe(200);
    ids.push((await response.json()).data.id);
    if (headers.length === 1) return route.abort('failed');
    await route.fulfill({ response });
  });
  await page.goto('/workspace/' + project + '/models');
  await page.getByRole('button', { name: 'Add credential', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'New credential', exact: true })).toBeFocused();
  const name = 'Test-only lost-response credential ' + Date.now();
  const fakeSecret = 'test-only-never-a-real-provider-key-' + Date.now();
  await page.getByLabel('Credential name', { exact: false }).fill(name);
  await page.getByLabel('Secret value', { exact: false }).fill(fakeSecret);
  const region = page.getByRole('region', { name: 'Project credentials', exact: true });
  await page.getByRole('button', { name: 'Save credential version', exact: true }).click();
  const feedback = region.getByRole('alert');
  await expect(feedback).toContainText('Save could not be confirmed');
  await expect(feedback).toBeFocused();
  await expect(feedback).toBeInViewport();
  await expect(page.getByLabel('Secret value', { exact: false })).toHaveValue(fakeSecret);
  await page.getByRole('button', { name: 'Save credential version', exact: true }).click();
  await expect(region.getByRole('status')).toContainText('Key saved securely: ' + name);
  await expect(region.getByRole('status')).toBeFocused();
  expect(headers).toHaveLength(2);
  expect(headers[0]).toBe(headers[1]);
  expect(ids[0]).toBe(ids[1]);
  await expect(region.getByRole('row').filter({ hasText: name })).toHaveCount(1);
  await page.reload();
  await expect(page.getByRole('button', { name: 'Add credential', exact: true })).toBeEnabled();
  while (!(await region.getByRole('row').filter({ hasText: name }).count())) {
    const count = await region.getByRole('row').count();
    await region.getByRole('button', { name: 'Load more credentials', exact: true }).click();
    await expect.poll(() => region.getByRole('row').count()).toBeGreaterThan(count);
  }
  await expect(region.getByRole('row').filter({ hasText: name })).toHaveCount(1);
  expect(await page.locator('body').innerText()).not.toContain(fakeSecret);
});
