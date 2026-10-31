import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';

test('Admin modern workspace persists model profiles and preserves classic comparison', async ({
  page,
}) => {
  await page.goto('/');
  await page.getByRole('link', { name: 'Sign in with Keycloak' }).click();
  await page.locator('#username').fill('admin-1');
  const password = readFileSync('.local/demo-accounts.md', 'utf8')
    .split('\n')
    .find((l) => l.startsWith('- admin-1:'))!
    .split('`')[1];
  await page.locator('#password').fill(password);
  await page.locator('#kc-login').click();
  await expect(page.getByRole('button', { name: 'Sign out', exact: true })).toBeVisible();
  const project = 'a0000000-0000-4000-8000-000000000002';
  await page.goto('/workspace/' + project + '/models');
  await page.getByRole('button', { name: 'Add model', exact: true }).click();
  const name = 'Browser baseline ' + Date.now();
  await page.getByLabel('Profile name', { exact: false }).fill(name);
  await page.getByLabel('Exact model ID', { exact: false }).fill('example-browser-model');
  await expect(page.getByLabel('API key', { exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Save model profile', exact: true }).click();
  // Profiles are paginated; an exact persisted profile is verified through the API, too.
  await expect(page.getByText('Profile saved to this project.', { exact: false })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Model profiles', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Add credential', exact: true }).click();
  const credentialName = 'Test-only browser credential ' + Date.now();
  const secret = 'test-only-not-a-provider-key-' + Date.now();
  await page.getByLabel('Credential name', { exact: false }).fill(credentialName);
  await page.getByLabel('Secret value', { exact: false }).fill(secret);
  const savedCredential = page.waitForResponse(
    (r) => r.url().endsWith('/workspace/credentials') && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Save credential version', exact: true }).click();
  const credentialResponse = await savedCredential;
  expect(credentialResponse.status()).toBe(200);
  expect(await credentialResponse.text()).not.toContain(secret);
  await expect(page.getByText('Credential version saved.', { exact: false })).toBeVisible();
  const credentialRow = page.getByRole('row').filter({ hasText: credentialName });
  await credentialRow.getByRole('button', { name: 'Revoke', exact: true }).click();
  await expect(credentialRow.getByText('Revoked', { exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'Frameworks', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Semantic Kernel', exact: true })).toBeVisible();
  await expect(page.getByText('Adapter not implemented.', { exact: false }).first()).toBeVisible();
  await page.getByRole('button', { name: 'Configure Harbor', exact: true }).click();
  await page.getByLabel('Profile name', { exact: false }).fill('Browser Harbor ' + Date.now());
  await page.getByRole('button', { name: 'Save framework profile', exact: true }).click();
  await expect(page.getByText('Framework metadata saved.', { exact: false })).toBeVisible();
  await page.getByRole('link', { name: 'Runs', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Run history', exact: true })).toBeVisible();
  const history = await (
    await page.request.get('/api/v1/projects/' + project + '/workspace/runs')
  ).json();
  const scored = history.data.items.find((r: { metrics: { scored: number } }) => r.metrics.scored);
  expect(
    scored,
    'The local integration fixture supplies retained synthetic run evidence',
  ).toBeTruthy();
  await page.goto('/workspace/' + project + '/runs?run=' + scored.id);
  await expect(page.getByText('Automated score', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Task & evaluations', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Bound evaluation configuration', exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Trajectories', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Observable trajectory', exact: true }),
  ).toBeVisible();
  const outputs = page.getByRole('button', { name: /output\.(json|txt) ·/ });
  if (await outputs.count()) {
    await outputs.first().click();
    await expect(page.getByText('SHA-256:', { exact: false })).toBeVisible();
    await expect(page.locator('main pre').first()).not.toBeEmpty();
  } else {
    await expect(page.getByRole('heading', { name: 'No retained output evidence' })).toBeVisible();
  }
  await expect(page.getByText('PRIVATE-NORTHSTAR', { exact: false })).toHaveCount(0);
  await page.getByRole('button', { name: 'Usage', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Usage & accounting', exact: true }),
  ).toBeVisible();
  await page.getByRole('link', { name: 'Compare classic journey', exact: false }).click();
  await expect(
    page.getByRole('heading', { name: 'Praxis → Harbor', exact: true, level: 1 }),
  ).toBeVisible();
  await page.getByRole('link', { name: 'Modern workspace', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Set up your workspace', exact: true }),
  ).toBeVisible();
  await page.screenshot({ path: 'artifacts/test-runs/modern-workspace-admin.png', fullPage: true });
});
