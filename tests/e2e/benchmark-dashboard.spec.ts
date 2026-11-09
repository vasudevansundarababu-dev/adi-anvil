import { test, expect, type Page } from '@playwright/test';
import { lstatSync, readFileSync } from 'node:fs';

const project = process.env.ANVIL_DASHBOARD_PROJECT_ID || 'a0000000-0000-4000-8000-000000000002';
const username = process.env.ANVIL_DASHBOARD_USERNAME || 'admin-1';
const deniedProject =
  process.env.ANVIL_DASHBOARD_DENIED_PROJECT_ID || 'a0000000-0000-4000-8000-000000000003';

function privatePassword() {
  const file = process.env.ANVIL_DASHBOARD_PASSWORD_FILE;
  if (file) {
    const metadata = lstatSync(file);
    if (
      !metadata.isFile() ||
      metadata.isSymbolicLink() ||
      metadata.mode & 0o077 ||
      (process.getuid && metadata.uid !== process.getuid())
    )
      throw new Error('Dashboard test password must be an owner-only regular file');
    return readFileSync(file, 'utf8').replace(/\r?\n$/, '');
  }
  const line = readFileSync(
    process.env.ANVIL_DASHBOARD_ACCOUNTS_FILE || '.local/demo-accounts.md',
    'utf8',
  )
    .split('\n')
    .find((value) => value.startsWith('- ' + username + ':'));
  if (!line) throw new Error('Dashboard test account is not configured');
  return line.split('`')[1];
}

// Actual isolated local OIDC/API records only. No route interception, synthetic
// score injection, approval simulation or provider invocation is used here.
async function signIn(page: Page) {
  await page.goto('/');
  await page.getByRole('link', { name: 'Sign in with Keycloak' }).click();
  await page.locator('#username').fill(username);
  await page.locator('#password').fill(privatePassword());
  await page.locator('#kc-login').click();
  await expect(page.getByRole('button', { name: 'Sign out', exact: true })).toBeVisible();
}

test('four connected benchmark views preserve real context and never create execution or reviews', async ({
  page,
}) => {
  await signIn(page);
  const root = '/workspace/' + project + '/benchmarks';
  const mutations: string[] = [];
  page.on('request', (request) => {
    if (
      request.url().includes('/workspace/benchmarks/') &&
      !['GET', 'HEAD'].includes(request.method())
    )
      mutations.push(request.url());
  });
  await page.goto(root + '?period=7d&environment=all');
  const response = await page.request.get(
    '/api/v1/projects/' + project + '/workspace/benchmarks/dashboard?period=7d&environment=all',
  );
  expect(response.status()).toBe(200);
  const stored = (await response.json()).data;
  expect(stored.schema_version).toBe('anvil-dashboard-v1');
  const workbench = page.getByRole('region', { name: 'Connected benchmark workbench' });
  await expect(
    workbench.getByRole('heading', { name: 'Overview & leaderboard', exact: true }),
  ).toBeVisible();
  await expect(workbench.getByLabel('Evaluation period')).toHaveValue('7d');
  await expect(workbench.getByLabel('Recorded environment')).toHaveValue('all');
  await expect(workbench).toContainText(stored.origin_notice);
  await expect(page.getByRole('complementary', { name: 'UI mockup disclosure' })).toHaveCount(0);
  for (const [label, suffix] of [
    ['Trace & rubric', 'trace'],
    ['Failure analysis', 'failures'],
    ['Remediation & datasets', 'remediation'],
    ['Overview & leaderboard', ''],
  ] as const) {
    await workbench
      .getByRole('navigation', { name: 'Benchmark views' })
      .getByRole('link', { name: label })
      .click();
    await expect.poll(() => new URL(page.url()).pathname).toBe(root + (suffix ? '/' + suffix : ''));
    expect(new URL(page.url()).searchParams.get('period')).toBe('7d');
    expect(new URL(page.url()).searchParams.get('environment')).toBe('all');
    await expect(workbench.getByRole('heading', { name: label, exact: true })).toBeVisible();
  }
  await page.reload();
  await expect(workbench.getByLabel('Evaluation period')).toHaveValue('7d');
  expect(mutations).toEqual([]);
  const denied = await page.request.get(
    '/api/v1/projects/' + deniedProject + '/workspace/benchmarks/dashboard',
  );
  expect([403, 404]).toContain(denied.status());
});

test('report export is an actual redacted snapshot-bound PDF and raw prompts remain disabled', async ({
  page,
}) => {
  await signIn(page);
  await page.goto('/workspace/' + project + '/benchmarks');
  await page.getByRole('button', { name: 'Export report' }).click();
  const dialog = page.getByRole('dialog', { name: 'Generate evaluation report' });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByLabel('Include raw prompts (unavailable)')).toBeDisabled();
  await expect(dialog.getByLabel('Include raw prompts (unavailable)')).not.toBeChecked();
  await dialog.getByLabel('Report template').selectOption('technical');
  const response = page.waitForResponse((item) =>
    item.url().includes('/workspace/benchmarks/dashboard/report?'),
  );
  const download = page.waitForEvent('download');
  await dialog.getByRole('button', { name: 'Download PDF report' }).click();
  const report = await response;
  expect(report.status()).toBe(200);
  expect(report.headers()['content-type']).toContain('application/pdf');
  const url = new URL(report.url());
  expect(url.searchParams.get('snapshot_sha256')).toMatch(/^[a-f0-9]{64}$/);
  expect(url.searchParams.get('template')).toBe('technical');
  expect(url.searchParams.get('include_raw_prompts')).toBe('false');
  const file = await download;
  expect(file.suggestedFilename()).toBe('anvil-technical-evaluation.pdf');
  const filePath = await file.path();
  expect(filePath).not.toBeNull();
  expect(readFileSync(filePath!).subarray(0, 4).toString()).toBe('%PDF');
});
