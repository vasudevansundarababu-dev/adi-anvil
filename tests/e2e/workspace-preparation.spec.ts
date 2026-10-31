import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';

test('Admin saves a typed preset and multi-model preparation without spending defaults or launch', async ({
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
                .find((value) => value.startsWith('anvil_csrf='))
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
  const stamp = String(Date.now());
  const runner = await post('/workspace/frameworks', {
    name: 'Browser runner ' + stamp,
    framework: 'harbor',
  });
  const models = [];
  for (const index of [1, 2])
    models.push(
      await post('/workspace/models', {
        name: 'Browser preparation model ' + stamp + ' ' + index,
        provider: 'openai',
        model_id: 'test-only-planning-' + index,
        max_output_tokens: 2048,
      }),
    );
  const sourceBody = JSON.parse(
    readFileSync('contracts/praxis/synthetic-marketing.task.json', 'utf8'),
  );
  sourceBody.task_id += '-planning-' + stamp;
  const source = await post('/praxis-sources', { payload: JSON.stringify(sourceBody) });
  const pack = await post('/praxis-sources/' + source.id + '/build', {});
  await page.goto('/workspace/' + project + '/frameworks');
  const presetRegion = page.getByRole('region', {
    name: 'Execution preset configuration',
    exact: true,
  });
  await expect(presetRegion).toHaveAttribute('aria-busy', 'false');
  const presetName = 'Browser execution preset ' + stamp;
  await page.getByLabel('Preset name', { exact: false }).fill(presetName);
  while (!(await page.locator('#preset-runner option[value="' + runner.id + '"]').count())) {
    const loaded = page.waitForResponse((r) => r.url().includes('/workspace/frameworks?after='));
    await page.getByRole('button', { name: 'Load more framework choices', exact: true }).click();
    await loaded;
    await expect(presetRegion).toHaveAttribute('aria-busy', 'false');
  }
  await page.getByLabel('Evaluation runner', { exact: false }).selectOption(runner.id);
  for (const model of models) {
    while (!(await page.getByLabel(model.name, { exact: false }).count())) {
      const loaded = page.waitForResponse(
        (r) => r.url().includes('/workspace/models?') && new URL(r.url()).searchParams.has('after'),
      );
      await page.getByRole('button', { name: 'Load more model choices', exact: true }).click();
      await loaded;
      await expect(presetRegion).toHaveAttribute('aria-busy', 'false');
    }
    await page.getByLabel(model.name, { exact: false }).check();
  }
  const presetResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith('/workspace/presets') && response.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Save execution preset', exact: true }).click();
  const savedPreset = await presetResponse;
  expect(savedPreset.status()).toBe(200);
  const preset = (await savedPreset.json()).data;
  await expect(page.getByText('Preset saved.', { exact: false })).toBeVisible();
  await page.goto(
    '/workspace/' + project + '/preparation?task=' + encodeURIComponent(source.task_id),
  );
  await expect(
    page.getByRole('heading', { name: 'Prepare model evaluation', exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel('Aggregate API budget', { exact: false })).toHaveValue('');
  const preparationRegion = page.getByRole('region', {
    name: 'Evaluation preparation',
    exact: true,
  });
  await expect(preparationRegion).toHaveAttribute('aria-busy', 'false');
  await page.getByLabel('Task package version', { exact: false }).selectOption(pack.id);
  while (!(await page.locator('#preparation-preset option[value="' + preset.id + '"]').count())) {
    const loaded = page.waitForResponse((r) => r.url().includes('/workspace/presets?after='));
    await page.getByRole('button', { name: 'Load more preset choices', exact: true }).click();
    await loaded;
    await expect(preparationRegion).toHaveAttribute('aria-busy', 'false');
  }
  await page.getByLabel('Execution preset', { exact: false }).selectOption(preset.id);
  for (const model of models) await page.getByLabel(model.name, { exact: false }).check();
  const preparationResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith('/workspace/preparations') && response.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Save preparation', exact: true }).click();
  const savedResponse = await preparationResponse;
  expect(savedResponse.status()).toBe(200);
  const saved = (await savedResponse.json()).data;
  expect(saved.snapshot.models).toHaveLength(2);
  expect(saved.snapshot.aggregate_cap_micro_usd).toBeNull();
  expect(saved.readiness.reservation_micro_usd).toBeNull();
  expect(saved.launch_available).toBe(false);
  await expect(page).toHaveURL(new RegExp('preparation=' + saved.id));
  await page.reload();
  await expect(
    page.getByRole('heading', { name: 'Preparation readiness', exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText('An explicit aggregate API cap is missing.', { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Launch unavailable', exact: true }),
  ).toBeDisabled();
  await page.getByRole('button', { name: 'Refresh preparation choices', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Preparation readiness', exact: true }),
  ).toBeVisible();
  await expect(preparationRegion).toHaveAttribute('aria-busy', 'false');
  await page.getByLabel('Task package version', { exact: false }).selectOption(pack.id);
  while (!(await page.locator('#preparation-preset option[value="' + preset.id + '"]').count())) {
    const loaded = page.waitForResponse((r) => r.url().includes('/workspace/presets?after='));
    await page.getByRole('button', { name: 'Load more preset choices', exact: true }).click();
    await loaded;
    await expect(preparationRegion).toHaveAttribute('aria-busy', 'false');
  }
  await page.getByLabel('Execution preset', { exact: false }).selectOption(preset.id);
  for (const model of models) await page.getByLabel(model.name, { exact: false }).check();
  await page.getByLabel('Aggregate API budget', { exact: false }).fill('0.012345');
  const boundedResponse = page.waitForResponse(
    (r) => r.url().endsWith('/workspace/preparations') && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Save preparation', exact: true }).click();
  const bounded = (await (await boundedResponse).json()).data;
  expect(bounded.snapshot.aggregate_cap_micro_usd).toBe(12345);
  expect(bounded.id).not.toBe(saved.id);
  const original = (
    await (await page.request.get(base + '/workspace/preparations/' + saved.id)).json()
  ).data;
  expect(original.snapshot.aggregate_cap_micro_usd).toBeNull();
  await expect(page.getByText('Aggregate budget: $0.012345.', { exact: false })).toBeVisible();
  await page.setViewportSize({ width: 320, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.getByRole('button', { name: 'Dark theme', exact: true }).click();
  await page.screenshot({
    path: 'artifacts/test-runs/modern-preparation-mobile.png',
    fullPage: true,
  });
});
