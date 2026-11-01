import { test, expect } from '@playwright/test';
import { readFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';

test('task library → version viewer → repeated run configuration and inert Dockerfile intake', async ({
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
  const base = '/api/v1/projects/' + project;
  const route = '/workspace/' + project;
  async function post(path: string, body: unknown) {
    return page.evaluate(
      async ({ path, body }) => {
        const response = await fetch(path, {
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
          body: JSON.stringify(body),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(JSON.stringify(result));
        return result.data;
      },
      { path: base + path, body },
    );
  }
  const stamp = Date.now();
  const fixture = JSON.parse(
    readFileSync('contracts/praxis/synthetic-marketing.task.json', 'utf8'),
  );
  fixture.task_id += '-screens-' + stamp;
  fixture.title = 'Marketing task screen ' + stamp;
  const source = await post('/praxis-sources', { payload: JSON.stringify(fixture) });
  const pack = await post('/praxis-sources/' + source.id + '/build', {});
  const model = await post('/workspace/models', {
    name: 'Screen model ' + stamp,
    provider: 'openai',
    model_id: 'gpt-6-luna',
    max_output_tokens: 1024,
  });
  const runner = await post('/workspace/frameworks', {
    name: 'Screen runner ' + stamp,
    framework: 'harbor',
  });
  const preset = await post('/workspace/presets', {
    name: 'Screen preset ' + stamp,
    runner_profile_id: runner.id,
    candidate_runtime: 'anvil-structured-json-v1',
    model_profile_ids: [model.id],
  });
  // Keep the real saved preset visible without depending on retained fixture pagination.
  await page.route('**/workspace/presets', async (route) => {
    if (route.request().method() !== 'GET') return route.continue();
    const response = await route.fetch();
    const body = await response.json();
    body.data = { items: [preset], next_cursor: null };
    await route.fulfill({ response, json: body });
  });
  await page.goto(route + '/tasks');
  await page.getByRole('searchbox', { name: 'Search tasks' }).fill(fixture.task_id);
  const row = page.getByRole('row').filter({ hasText: fixture.title });
  await expect(row).toHaveCount(1);
  await expect(row.getByText('Package built', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Dark theme', exact: true }).click();
  await page.screenshot({ path: 'artifacts/test-runs/task-library.png', fullPage: true });
  await row.getByRole('link', { name: 'View', exact: true }).click();
  await expect(page.getByRole('heading', { name: fixture.title, exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Light theme', exact: true })).toBeVisible();
  for (const name of ['MCP / Tool calls', 'Input files', 'Rubrics', 'Verifiers', 'Task']) {
    await page.getByRole('button', { name, exact: true }).click();
    await expect(page.getByRole('button', { name, exact: true })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  }
  expect(await page.locator('main').innerText()).not.toContain('PRIVATE-NORTHSTAR');
  const folder = resolve('artifacts/test-runs/environment-' + stamp);
  mkdirSync(folder + '/inputs', { recursive: true });
  writeFileSync(folder + '/Dockerfile', 'FROM python:3.12-slim\nCOPY inputs/ /app/inputs/\n');
  writeFileSync(folder + '/inputs/facts.txt', 'Synthetic test inputs');
  await page.getByLabel('Environment name', { exact: true }).fill('Browser environment ' + stamp);
  const envResponse = page.waitForResponse(
    (r) => r.url().endsWith('/environments') && r.request().method() === 'POST',
  );
  await page.getByLabel('Environment folder', { exact: true }).setInputFiles(folder);
  expect((await envResponse).status()).toBe(200);
  await expect(
    page.getByText('Imported · Awaiting environment qualification', { exact: true }),
  ).toBeVisible();
  await page.screenshot({ path: 'artifacts/test-runs/task-view.png', fullPage: true });
  await page.getByRole('link', { name: 'Run task', exact: false }).click();
  await expect(
    page.getByRole('region', { name: 'Evaluation preparation', exact: true }),
  ).toHaveAttribute('aria-busy', 'false');
  await expect(page.locator('#preparation-package')).toHaveValue(pack.id);
  await expect(page.getByLabel('Target environment', { exact: true })).toHaveValue(
    'package-docker',
  );
  await expect(
    page.getByRole('option', {
      name: 'Browser environment ' + stamp + ' · Awaiting qualification',
    }),
  ).toBeDisabled();
  await page.getByLabel(model.name, { exact: false }).check();
  await page.getByLabel('Repetitions per model', { exact: false }).fill('3');
  await page.getByLabel('Selected maximum output tokens', { exact: false }).fill('1024');
  await page.getByLabel('Aggregate API budget', { exact: false }).fill('1');
  await page.screenshot({ path: 'artifacts/test-runs/task-run-configuration.png', fullPage: true });
  const groupResponse = page.waitForResponse(
    (r) => r.url().endsWith('/execution-groups') && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Create execution group', exact: true }).click();
  const response = await groupResponse;
  expect(response.status()).toBe(200);
  const group = (await response.json()).data;
  await expect(page).toHaveURL(new RegExp('/tasks/' + source.id + '/run\\?group=' + group.id));
  expect(group.models).toHaveLength(3);
  expect(group.snapshot.preparation.trials_per_model).toBe(3);
  await expect(page.getByRole('button', { name: 'Run', exact: true })).toBeDisabled();
  await expect(page.getByRole('region', { name: 'Execution live log' })).toContainText(
    'Configuration saved.',
  );
  const refreshed = page.waitForResponse(
    (r) => r.url().endsWith('/execution-groups') && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Update configuration', exact: true }).click();
  expect((await refreshed).status()).toBe(200);
  await expect(page).not.toHaveURL(new RegExp('group=' + group.id + '$'));
  await expect(page).toHaveURL(new RegExp('/tasks/' + source.id + '/run\\?group='));
  await expect(page.getByRole('button', { name: 'Run', exact: true })).toBeDisabled();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: 'artifacts/test-runs/task-run-mobile.png', fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
});
