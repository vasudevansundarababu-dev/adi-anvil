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
  const credential = await post('/workspace/credentials', {
    name: 'Screen linked key ' + stamp,
    provider: 'openai',
    secret: 'test-only-not-a-real-key-' + stamp,
  });
  const extraModel = await post('/workspace/models', {
    name: 'Secondary linked profile ' + stamp,
    provider: 'openai',
    model_id: 'gpt-6-luna',
    max_output_tokens: 1024,
    credential_id: credential.id,
  });
  // Two real persisted models split over controlled metadata pages. The second
  // model is intentionally outside the original preset's immutable allowlist.
  await page.route(
    (url) =>
      url.pathname.endsWith('/workspace/models') && url.searchParams.get('current_only') === 'true',
    async (route) => {
      const response = await route.fetch();
      const body = await response.json();
      const after = new URL(route.request().url()).searchParams.has('after');
      body.data = {
        items: after ? [extraModel] : [model],
        next_cursor: after ? null : extraModel.profile_id,
      };
      await route.fulfill({ response, json: body });
    },
  );
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
  await expect(page.getByRole('button', { name: 'Refresh tasks', exact: true })).toHaveCount(0);
  await expect(
    page
      .getByRole('region', { name: 'Task library' })
      .getByRole('link', { name: 'Run history', exact: true }),
  ).toHaveCount(0);
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
  await expect(
    page.getByRole('button', { name: 'Refresh preparation choices', exact: true }),
  ).toHaveCount(0);
  await expect(page.getByLabel(extraModel.name, { exact: false })).toBeVisible();
  await expect(page.getByText('Key: ' + credential.name, { exact: true })).toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Settings for all selected models', exact: true }),
  ).toBeVisible();
  await expect(page.getByRole('button', { name: 'Run', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Run', exact: true }).click();
  await expect(page.locator('main').getByRole('alert')).toContainText('Aggregate API budget');
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
  // Missing model choice must produce an explanation instead of a disabled action.
  await page.getByLabel(model.name, { exact: false }).uncheck();
  await page.getByRole('button', { name: 'Run', exact: true }).click();
  await expect(page.locator('main').getByRole('alert')).toContainText('select at least one model');
  await page.getByLabel(model.name, { exact: false }).check();
  await page.screenshot({ path: 'artifacts/test-runs/task-run-configuration.png', fullPage: true });
  const groupResponse = page.waitForResponse(
    (r) => r.url().endsWith('/execution-groups') && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Run', exact: true }).click();
  const response = await groupResponse;
  expect(response.status()).toBe(200);
  const group = (await response.json()).data;
  await expect(page).toHaveURL(new RegExp('/tasks/' + source.id + '/run\\?group=' + group.id));
  expect(group.models).toHaveLength(3);
  expect(group.snapshot.preparation.trials_per_model).toBe(3);
  await expect(page.getByRole('button', { name: 'Run', exact: true })).toBeEnabled();
  await expect(
    page.getByRole('heading', { name: 'Run cannot start yet', exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Run', exact: true }).click();
  await expect(page.locator('main').getByRole('alert')).toContainText('saved API key');
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
  await expect(page.getByRole('button', { name: 'Run', exact: true })).toBeEnabled();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: 'artifacts/test-runs/task-run-mobile.png', fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );

  // Browser-only ready/launch fixtures verify direct Run wiring. No launch request
  // reaches the backend or a provider; persisted synthetic groups remain drafts.
  await page.setViewportSize({ width: 1280, height: 900 });
  let readyGroup: any = null;
  let launchCount = 0;
  await page.route('**/workspace/execution-groups', async (route) => {
    if (route.request().method() !== 'POST') return route.continue();
    const response = await route.fetch();
    const body = await response.json();
    body.data.readiness.missing = ['admin_run_authorization_required'];
    body.data.readiness.models.forEach((m: { missing: string[] }) => {
      m.missing = [];
    });
    readyGroup = body.data;
    await route.fulfill({ response, json: body });
  });
  await page.route('**/workspace/execution-groups/*', async (route) => {
    if (
      !readyGroup ||
      !route
        .request()
        .url()
        .endsWith('/' + readyGroup.id)
    )
      return route.continue();
    await route.fulfill({ json: { data: readyGroup } });
  });
  await page.route('**/workspace/execution-groups/*/launch', async (route) => {
    launchCount++;
    expect(route.request().postDataJSON()).toEqual({
      subject_hash: readyGroup.subject_hash,
      aggregate_cap_micro_usd: 1000000,
      rights_confirmed: true,
    });
    readyGroup = {
      ...readyGroup,
      state: 'launched',
      status: 'queued',
      models: readyGroup.models.map((m: any) => ({
        ...m,
        check: { id: m.plan_id, state: 'queued', error_code: null },
      })),
    };
    await route.fulfill({ json: { data: readyGroup } });
  });
  await page.route('**/workspace/runs/*', async (route) => {
    const member = readyGroup?.models.find((m: any) =>
      route
        .request()
        .url()
        .endsWith('/' + m.plan_id),
    );
    if (!member) return route.continue();
    await route.fulfill({
      json: {
        data: {
          id: member.plan_id,
          task_id: source.task_id,
          model: 'Synthetic browser launch fixture',
          trial: member.trial,
          state: 'queued',
          created_at: new Date().toISOString(),
          metrics: { score: null },
        },
      },
    });
  });
  await page.goto(route + '/tasks/' + source.id + '/run');
  await expect(
    page.getByRole('region', { name: 'Evaluation preparation', exact: true }),
  ).toHaveAttribute('aria-busy', 'false');
  await page.getByLabel(model.name, { exact: false }).check();
  await page.getByLabel(extraModel.name, { exact: false }).check();
  await page.getByLabel('Selected maximum output tokens', { exact: false }).fill('1024');
  await page.getByLabel('Aggregate API budget', { exact: false }).fill('1');
  await page.getByLabel('Repetitions per model', { exact: false }).fill('2');
  await page.getByLabel('Episode time limit', { exact: false }).fill('60');
  const preparationRequest = page.waitForResponse(
    (r) => r.url().endsWith('/workspace/preparations') && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Run', exact: true }).click();
  const configured = (await preparationRequest).request().postDataJSON();
  expect(configured.model_profile_ids).toEqual([model.id, extraModel.id]);
  expect(configured).toMatchObject({
    max_output_tokens: 1024,
    trials_per_model: 2,
    episode_timeout_seconds: 60,
    aggregate_cap_micro_usd: 1000000,
  });
  await expect(page).toHaveURL(new RegExp('/run\\?group='));
  expect(readyGroup.models).toHaveLength(4);
  expect(launchCount).toBe(1);
  await expect(page.getByRole('region', { name: 'Execution live log' })).toContainText(
    'Synthetic browser launch fixture',
  );
  await expect(page.getByRole('button', { name: 'Run', exact: true })).toHaveCount(0);
});
