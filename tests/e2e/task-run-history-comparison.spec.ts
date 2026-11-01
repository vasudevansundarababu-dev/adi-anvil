import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';

test('task run history owns comparison and Runs is absent from the sidebar', async ({ page }) => {
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
  const fixture = JSON.parse(
    readFileSync('contracts/praxis/synthetic-marketing.task.json', 'utf8'),
  );
  fixture.task_id += '-history-' + Date.now();
  const source = await page.evaluate(
    async ({ project, fixture }) => {
      const response = await fetch('/api/v1/projects/' + project + '/praxis-sources', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Idempotency-Key': crypto.randomUUID(),
          'X-CSRF-Token':
            document.cookie
              .split('; ')
              .find((v) => v.startsWith('anvil_csrf='))
              ?.split('=')[1] || '',
        },
        body: JSON.stringify({ payload: JSON.stringify(fixture) }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(JSON.stringify(result));
      return result.data;
    },
    { project, fixture },
  );
  // Explicit browser-only software fixtures exercise comparisons; no results or
  // model calls are written to the project database.
  const runs = [50, 80].map((score, index) => ({
    id: index ? '22222222-2222-4222-8222-222222222222' : '11111111-1111-4111-8111-111111111111',
    title: 'Synthetic comparison fixture',
    task_id: source.task_id,
    task_version: source.task_version,
    model: 'Fixture ' + (index + 1),
    candidate: 'reference',
    state: 'succeeded',
    origin: 'synthetic_software_verification',
    created_at: '2026-11-01T12:00:00Z',
    started_at: '2026-11-01T12:00:00Z',
    finished_at: '2026-11-01T12:00:01Z',
    comparison_signature: 'a'.repeat(64),
    metrics: {
      score,
      reward: score / 100,
      scored: 1,
      attempts: 1,
      passed: 0,
      task_failed: 1,
      execution_errors: 0,
      unknown: 0,
      elapsed_seconds: 1,
      known_cost_micro_usd: 0,
      cost_complete: true,
      reserved_micro_usd: 0,
    },
  }));
  await page.route(
    (url) =>
      url.pathname.endsWith('/workspace/runs') &&
      url.searchParams.get('task_id') === source.task_id,
    async (route) =>
      route.fulfill({ json: { data: { items: runs, next_cursor: null, scope: 'praxis_harbor' } } }),
  );
  await page.goto('/workspace/' + project + '/tasks/' + source.id);
  await expect(
    page
      .getByRole('navigation', { name: 'Workspace navigation' })
      .getByRole('link', { name: 'Runs', exact: true }),
  ).toHaveCount(0);
  await page.getByRole('link', { name: 'Run history', exact: false }).click();
  await expect(page).toHaveURL(new RegExp('/runs\\?task='));
  const history = page.getByRole('region', { name: 'Run history', exact: true });
  await expect(history).toContainText('Select two or more runs');
  await expect(
    history.getByRole('button', { name: 'Compare selected (0)', exact: true }),
  ).toBeDisabled();
  await history.getByRole('checkbox', { name: 'Select run 11111111', exact: true }).check();
  await history.getByRole('checkbox', { name: 'Select run 22222222', exact: true }).check();
  await history.getByRole('button', { name: 'Compare selected (2)', exact: true }).click();
  await expect(history.getByRole('heading', { name: 'Compare runs', exact: true })).toBeVisible();
  await expect(history.getByRole('cell', { name: '30.00 points', exact: true })).toBeVisible();
  await history.getByRole('checkbox', { name: 'Select run 22222222', exact: true }).uncheck();
  await expect(history).toContainText('Select at least two runs');
  await history.getByRole('button', { name: 'Close comparison', exact: true }).click();
  await expect(history.getByRole('heading', { name: 'Compare runs', exact: true })).toHaveCount(0);
});
