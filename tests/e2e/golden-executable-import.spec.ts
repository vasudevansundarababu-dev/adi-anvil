import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';

test('all three golden exports import without exposing private oracles or claiming runnable readiness', async ({
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
  for (const file of [
    '01-marketing.export.json',
    '02-kyc_aml.export.json',
    '03-fraud.export.json',
  ]) {
    const path = 'contracts/praxis/golden-v3/' + file;
    const payload = JSON.parse(JSON.parse(readFileSync(path, 'utf8')).payload_json);
    await page.goto('/workspace/' + project + '/tasks/import');
    const saved = page.waitForResponse(
      (r) => r.url().endsWith('/praxis-sources') && r.request().method() === 'POST',
    );
    await page.getByLabel('Praxis task export (.json)', { exact: false }).setInputFiles(path);
    const response = await saved;
    expect(response.status()).toBe(200);
    const value = (await response.json()).data;
    expect(value.executable_import.ready).toBe(false);
    await expect(
      page.getByRole('heading', { name: 'Make this task executable', exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole('heading', { name: 'Live import progress', exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole('button', { name: 'Build Harbor package', exact: true }),
    ).toHaveCount(0);
    await expect(page.getByLabel('Environment folder', { exact: true })).toHaveCount(0);
    expect(await page.locator('main').innerText()).not.toContain(payload.evaluation_private.canary);
    await page.getByRole('link', { name: 'View imported task', exact: true }).click();
    await expect(page.getByRole('heading', { name: payload.title, exact: true })).toBeVisible();
    await expect(page.getByText('anvil-golden-tools:1.0.0', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Rubrics', exact: true }).click();
    expect(await page.locator('main').innerText()).not.toContain(payload.evaluation_private.canary);
    await page.getByRole('link', { name: 'Complete run setup', exact: true }).click();
    await expect(
      page.getByText('Not ready to run · Generation and validation required', { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole('heading', {
        name: 'Complete executable generation first',
        exact: true,
      }),
    ).toBeVisible();
    await expect(page.getByRole('button', { name: 'Run', exact: true })).toHaveCount(0);
    await expect(
      page.getByText('Choose at least one model and enter a budget', { exact: false }),
    ).toHaveCount(0);
    await expect(
      page.getByRole('heading', { name: 'Make this task executable', exact: true }),
    ).toBeVisible();
  }
});

test('generated-import UI safely retries a lost response and downloads its notebook from the API', async ({
  page,
}) => {
  // Controlled UI response states only. Real backend/native generation is covered by
  // test_import_pipeline.py; these interceptions make no paid request or persisted Ready claim.
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
  const response = await page.request.get(
    '/api/v1/projects/' + project + '/workspace/tasks?search=GOLDEN-MARKETING',
  );
  const source = (await response.json()).data.items.find(
    (t: any) => t.task_id === 'GOLDEN-MARKETING',
  );
  expect(source).toBeTruthy();
  const settingsId = '10000000-0000-4000-8000-000000000001';
  const importId = '10000000-0000-4000-8000-000000000002';
  const revisionId = '10000000-0000-4000-8000-000000000003';
  let family: any = null;
  const keys: string[] = [];
  await page.route('**/workspace/import-generation/settings', (route) =>
    route.fulfill({
      json: {
        data: {
          configured: true,
          can_configure: false,
          can_authorize_processing: true,
          paid_generation_enabled: false,
          id: settingsId,
          provider: 'openai',
          model_id: 'software-ui-fixture',
          default_cap_micro_usd: 1000,
        },
      },
    }),
  );
  await page.route('**/workspace/tasks/' + source.id + '/executable-import', (route) =>
    route.fulfill({ json: { data: family } }),
  );
  await page.route('**/workspace/tasks/' + source.id + '/generate', async (route) => {
    keys.push(route.request().headers()['idempotency-key']);
    expect(route.request().postDataJSON().source_sha256).toBe(source.source_sha256);
    if (keys.length === 1) {
      await route.abort('failed');
      return;
    }
    family = {
      id: importId,
      source_id: source.id,
      settings_id: settingsId,
      current_revision_id: revisionId,
      ready_revision_id: revisionId,
      cap_micro_usd: 1000,
      charged_micro_usd: 0,
      reserved_micro_usd: 0,
      remaining_micro_usd: 1000,
      generation_model: { provider: 'openai', model_id: 'software-ui-fixture' },
      revisions: [{ id: revisionId, state: 'ready', kind: 'generate', report: {} }],
    };
    await route.fulfill({ json: { data: family } });
  });
  await page.route(
    '**/workspace/executable-imports/' + importId + '/revisions/' + revisionId + '/notebook',
    (route) =>
      route.fulfill({
        contentType: 'application/x-ipynb+json',
        headers: { 'Content-Disposition': 'attachment; filename="anvil-review.ipynb"' },
        body: JSON.stringify({ nbformat: 4, nbformat_minor: 5, metadata: {}, cells: [] }),
      }),
  );
  await page.goto('/workspace/' + project + '/tasks/' + source.id);
  const generate = page.getByRole('button', { name: 'Import & generate', exact: true });
  await generate.click();
  await expect(page.getByRole('alert').filter({ hasText: 'Failed to fetch' })).toBeVisible();
  await expect(generate).toBeEnabled();
  await generate.click();
  await expect(
    page.getByRole('link', { name: 'Download review notebook', exact: true }),
  ).toBeVisible();
  await expect(page.getByText('Import generation complete', { exact: true })).toBeVisible();
  family.revisions[0] = {
    id: revisionId,
    state: 'validating',
    report: { stage: 'package_smoke' },
  };
  family.ready_revision_id = null;
  await page.reload();
  await expect(page.getByText('Import generation in progress', { exact: false })).toBeVisible();
  await expect(page.getByText('In progress: Running Harbor package checks')).toBeVisible();
  family.revisions[0].state = 'ready';
  family.ready_revision_id = revisionId;
  await expect(page.getByText('Import generation complete', { exact: true })).toBeVisible();
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
  const download = page.waitForEvent('download');
  await page.getByRole('link', { name: 'Download review notebook', exact: true }).click();
  expect((await download).suggestedFilename()).toBe('anvil-review.ipynb');
});

test('golden ungenerated tasks show plain-language import explanations on list and detail', async ({
  page,
}) => {
  await page.goto('/');
  await page.getByRole('link', { name: 'Sign in with Keycloak' }).click();
  await page.locator('#username').fill('researcher');
  const password = readFileSync('.local/demo-accounts.md', 'utf8')
    .split('\n')
    .find((line) => line.startsWith('- researcher:'))!
    .split('`')[1];
  await page.locator('#password').fill(password);
  await page.locator('#kc-login').click();
  await expect(page.getByRole('button', { name: 'Sign out', exact: true })).toBeVisible();
  const project = 'a0000000-0000-4000-8000-000000000002';
  const rawCode = /\b[a-z]+(_[a-z]+)+\b/;
  const payload = JSON.parse(
    JSON.parse(readFileSync('contracts/praxis/golden-v3/01-marketing.export.json', 'utf8'))
      .payload_json,
  );
  await page.goto('/workspace/' + project + '/tasks');
  await page.getByLabel('Search tasks', { exact: false }).fill(payload.title);
  const row = page.getByRole('row').filter({ hasText: payload.title }).first();
  await expect(row).toBeVisible();
  const cell = row.getByRole('cell').first();
  await expect(cell).toContainText('Needs generation');
  await expect(cell).toContainText(
    'No validated executable yet. Open the task to start generation.',
  );
  const text = (await cell.innerText()).replace(payload.task_id, '');
  expect(text).not.toMatch(rawCode);
  expect(text).not.toContain(payload.evaluation_private.canary);
  await row.getByRole('link', { name: 'View', exact: true }).click();
  await expect(page.getByRole('heading', { name: payload.title, exact: true })).toBeVisible();
  await expect(
    page
      .getByRole('status')
      .filter({ hasText: 'Not ready to run · Generation and validation required' }),
  ).toHaveText('Not ready to run · Generation and validation required');
  await expect(
    page.getByRole('heading', { name: 'Make this task executable', exact: true }),
  ).toBeVisible();
});
