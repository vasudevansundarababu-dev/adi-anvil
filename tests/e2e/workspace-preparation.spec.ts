import { test, expect, type Browser } from '@playwright/test';
import { readFileSync } from 'node:fs';

test('saving a Harbor framework immediately populates the runner without resetting the preset form', async ({
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
  let saved: { id: string; framework: string; name: string } | null = null;
  // Isolate the list from retained fixtures, but save through the real authorized API.
  await page.route('**/workspace/frameworks', async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    if (route.request().method() === 'POST') saved = body.data;
    else body.data = { items: saved ? [saved] : [], next_cursor: null };
    await route.fulfill({ response, json: body });
  });
  await page.goto('/workspace/' + project + '/frameworks');
  await expect(page.getByText('No Harbor runner profiles loaded.', { exact: false })).toBeVisible();
  const runner = page.getByRole('combobox', { name: 'Evaluation runner', exact: false });
  await expect(runner.locator('option')).toHaveCount(1);
  await page.getByLabel('Preset name', { exact: false }).fill('Preserve this preset name');
  await page.getByRole('button', { name: 'Configure Harbor', exact: true }).click();
  const name = 'Browser auto-refresh runner ' + Date.now();
  await page.getByLabel('Profile name', { exact: false }).fill(name);
  await page.getByRole('button', { name: 'Save framework profile', exact: true }).click();
  await expect(runner.locator('option').filter({ hasText: name })).toHaveCount(1);
  await expect(page.getByText('No Harbor runner profiles loaded.', { exact: false })).toHaveCount(
    0,
  );
  await expect(page.getByLabel('Preset name', { exact: false })).toHaveValue(
    'Preserve this preset name',
  );
  expect(saved?.framework).toBe('harbor');
  await runner.selectOption(saved!.id);
  await expect(runner).toHaveValue(saved!.id);
});

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
    '/workspace/' + project + '/execution-groups/new?task=' + encodeURIComponent(source.task_id),
  );
  await expect(
    page.getByRole('heading', { name: 'Create execution group', exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel('Aggregate API budget', { exact: false })).toHaveValue('');
  const preparationRegion = page.getByRole('region', {
    name: 'Evaluation preparation',
    exact: true,
  });
  await expect(preparationRegion).toHaveAttribute('aria-busy', 'false');
  async function choosePackage() {
    const field = page.locator('#preparation-package');
    if (await field.evaluate((element) => element.tagName === 'SELECT'))
      await field.selectOption(pack.id);
    else {
      await expect(field).toHaveAttribute('type', 'hidden');
      await expect(field).toHaveValue(pack.id);
      await expect(
        page.getByRole('combobox', { name: 'Task package version', exact: false }),
      ).toHaveCount(0);
    }
  }
  async function choosePreset() {
    const field = page.locator('#preparation-preset');
    if (await field.evaluate((element) => element.tagName === 'SELECT')) {
      while (
        !(await page.locator('#preparation-preset option[value="' + preset.id + '"]').count())
      ) {
        const loaded = page.waitForResponse((r) => r.url().includes('/workspace/presets?after='));
        await page.getByRole('button', { name: 'Load more preset choices', exact: true }).click();
        await loaded;
        await expect(preparationRegion).toHaveAttribute('aria-busy', 'false');
      }
      await field.selectOption(preset.id);
    } else await expect(field).toHaveValue(preset.id);
  }
  await choosePackage();
  await choosePreset();
  for (const model of models) await page.getByLabel(model.name, { exact: false }).check();
  await page.getByLabel('Aggregate API budget', { exact: false }).fill('0.012345');
  const groupResponse = page.waitForResponse(
    (r) => r.url().endsWith('/workspace/execution-groups') && r.request().method() === 'POST',
  );
  const preparationResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith('/workspace/preparations') && response.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Create execution group', exact: true }).click();
  const savedResponse = await preparationResponse;
  expect(savedResponse.status()).toBe(200);
  const saved = (await savedResponse.json()).data;
  expect(saved.snapshot.models).toHaveLength(2);
  expect(saved.snapshot.aggregate_cap_micro_usd).toBe(12345);
  let group = (await (await groupResponse).json()).data;
  await expect(page).toHaveURL(new RegExp('/execution-groups/' + group.id + '$'));
  await expect(
    page.getByRole('heading', { name: 'Execution group ' + group.id.slice(0, 8), exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole('region', { name: 'Evaluation preparation', exact: true }),
  ).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Run', exact: true })).toBeEnabled();
  await expect(
    page.getByRole('heading', { name: 'Run cannot start yet', exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: 'Create execution group', exact: true }),
  ).toHaveCount(0);
  const originalGroup = group;
  const updateResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith('/workspace/execution-groups') &&
      response.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Update configuration', exact: true }).click();
  expect((await updateResponse).status()).toBe(200);
  await expect(page).not.toHaveURL(new RegExp('/execution-groups/' + originalGroup.id + '$'));
  await expect(page).toHaveURL(/\/execution-groups\/[a-f0-9-]+$/);
  const updatedId = new URL(page.url()).pathname.split('/').pop();
  group = (await (await page.request.get(base + '/workspace/execution-groups/' + updatedId)).json())
    .data;
  expect(group.id).not.toBe(originalGroup.id);
  expect(group.preparation_id).toBe(originalGroup.preparation_id);
  expect(group.snapshot.preparation).toEqual(originalGroup.snapshot.preparation);
  expect(group.reservation_retained).toBe(false);
  expect(group.models.every((model: { check: unknown }) => model.check === null)).toBe(true);
  await expect(page).toHaveURL(new RegExp('/execution-groups/' + group.id + '$'));
  const original = (
    await (await page.request.get(base + '/workspace/execution-groups/' + originalGroup.id)).json()
  ).data;
  expect(original.snapshot).toEqual(originalGroup.snapshot);
  expect(original.state).toBe('draft');
  await page.getByRole('link', { name: '← Execution groups', exact: true }).click();
  await expect(page).toHaveURL(new RegExp('/execution-groups$'));
  await expect(
    page.getByRole('region', { name: 'Evaluation preparation', exact: true }),
  ).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'Model runs', exact: true })).toHaveCount(0);
  await expect(
    page.getByRole('link', { name: 'Create execution group', exact: true }),
  ).toBeVisible();
  await page
    .getByRole('link', { name: 'Execution group ' + group.id.slice(0, 8), exact: true })
    .click();
  await expect(page.getByRole('heading', { name: 'Model runs', exact: true })).toBeVisible();
  for (const width of [320, 768, 1440]) {
    await page.setViewportSize({ width, height: 844 });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
  }
  await page.setViewportSize({ width: 1440, height: 1200 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: 'artifacts/test-runs/modern-execution-group-separated.png',
    fullPage: false,
  });
});

const readinessProject = 'a0000000-0000-4000-8000-000000000002';
const READINESS_RAW_CODE = /\b[a-z]+(_[a-z]+)+\b/;

async function readinessSignIn(browser: Browser, username: string) {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto('/');
  await page.getByRole('link', { name: 'Sign in with Keycloak' }).click();
  await page.locator('#username').fill(username);
  const password = readFileSync('.local/demo-accounts.md', 'utf8')
    .split('\n')
    .find((line) => line.startsWith('- ' + username + ':'))!
    .split('`')[1];
  await page.locator('#password').fill(password);
  await page.locator('#kc-login').click();
  await expect(page.getByRole('button', { name: 'Sign out', exact: true })).toBeVisible();
  return { context, page };
}

// Browser-only fixture: the same synthetic draft group is shown to both roles with fixed
// blockers. No launch request is sent and no provider is contacted.
const readinessBlockedGroup = {
  id: 'b0000000-0000-4000-8000-00000000a001',
  preparation_id: 'b0000000-0000-4000-8000-00000000a002',
  subject_hash: 'synthetic',
  state: 'draft',
  status: 'draft',
  readiness: {
    ready: false,
    missing: ['admin_run_authorization_required', 'aggregate_api_cap_missing', 'future_gate'],
    aggregate_cap_micro_usd: null,
    conservative_cost_micro_usd: null,
    models: [{ model_profile_id: 'm1', missing: ['credential_missing'] }],
  },
  models: [
    {
      trial: 1,
      plan_id: 'p1',
      model: { id: 'm1', name: 'Synthetic model', provider: 'openai', model_id: 'synthetic' },
      check: null,
    },
  ],
  snapshot: {
    preparation: {
      package: { manifest: { task_id: 'synthetic-task', task_version: '1' } },
      preset: { name: 'Synthetic preset' },
    },
  },
};

test('Admin and Engineer see plain-language blockers with the right fixer for the same group', async ({
  browser,
}) => {
  for (const [username, admin] of [
    ['admin-1', true],
    ['researcher', false],
  ] as const) {
    const { context, page } = await readinessSignIn(browser, username);
    let launches = 0;
    await page.route('**/workspace/execution-groups/' + readinessBlockedGroup.id, (route) =>
      route.fulfill({ json: { data: readinessBlockedGroup } }),
    );
    await page.route('**/workspace/execution-groups/*/launch', (route) => {
      launches++;
      return route.abort();
    });
    await page.goto(
      '/workspace/' + readinessProject + '/execution-groups/' + readinessBlockedGroup.id,
    );
    const panel = page
      .getByRole('status')
      .filter({ has: page.getByRole('heading', { name: 'Run cannot start yet', exact: true }) });
    await expect(panel).toBeVisible();
    await expect(panel).toHaveAttribute('tabindex', '-1');
    const items = panel.getByRole('listitem');
    await expect(items).toHaveCount(admin ? 3 : 4);
    for (const text of await items.allInnerTexts()) {
      const main = text.split('\n')[0];
      expect(main, 'main blocker text').not.toMatch(READINESS_RAW_CODE);
    }
    await expect(panel).toContainText(
      "This run is blocked by a condition Anvil can't describe yet.",
    );
    await expect(panel.getByText('Diagnostic code: future_gate', { exact: true })).toBeVisible();
    await expect(panel).toContainText('No aggregate API budget is set.');
    const workspace = '/workspace/' + readinessProject;
    const groupPage = workspace + '/execution-groups/' + readinessBlockedGroup.id;
    const expectedLinks: [string, string, string][] = admin
      ? [
          [
            'No aggregate API budget is set.',
            'Change run configuration',
            workspace + '/execution-groups/new',
          ],
          ["can't describe yet", 'Link to this page for your Anvil administrator', groupPage],
          ['This model has no saved API key.', 'Open Models & keys', workspace + '/models'],
        ]
      : [
          ['An Admin must start this run', 'Link to this page for a project Admin', groupPage],
          [
            'No aggregate API budget is set.',
            'Change run configuration',
            workspace + '/execution-groups/new',
          ],
          ["can't describe yet", 'Link to this page for a project Admin', groupPage],
          ['Ask a project Admin to link one', 'Link to this page for a project Admin', groupPage],
        ];
    for (const [index, [text, name, href]] of expectedLinks.entries()) {
      const item = items.nth(index);
      await expect(item).toContainText(text);
      const links = item.getByRole('link');
      await expect(links).toHaveCount(1);
      await expect(links.first()).toHaveAccessibleName(name);
      await expect(links.first()).toHaveAttribute('href', href);
    }
    await expect(panel.getByRole('link')).toHaveCount(expectedLinks.length);
    if (admin) {
      await expect(panel).toContainText('Who can fix: you (Admin)');
      await expect(panel).not.toContainText('An Admin must start this run');
    } else {
      await expect(panel).toContainText('An Admin must start this run to authorize its budget.');
      await expect(panel).toContainText('Ask a project Admin to link one in Models & keys.');
      await expect(panel).toContainText('Who can fix: a project Admin');
      await expect(page.locator('a[href$="/models"], a[href$="/frameworks"]')).toHaveCount(0);
      await expect(page.locator('a[href="#execution-group-run"]')).toHaveCount(0);
    }
    if (admin) {
      await panel.getByRole('link', { name: 'Open Models & keys', exact: true }).click();
      await expect(page).toHaveURL(new RegExp(workspace + '/models$'));
      await expect(page.getByRole('heading', { name: 'Models & keys' }).first()).toBeVisible();
      await page.goBack();
      await expect(panel).toBeVisible();
    } else {
      await items.nth(0).getByRole('link').click();
      await expect(page).toHaveURL(new RegExp(groupPage + '$'));
      await expect(panel).toBeVisible();
    }
    await page.getByRole('button', { name: 'Run', exact: true }).click();
    await expect(panel).toHaveCount(0);
    const alert = page
      .getByRole('alert')
      .filter({ has: page.getByRole('heading', { name: 'Run cannot start yet', exact: true }) });
    await expect(alert).toBeFocused();
    expect(launches).toBe(0);
    await context.close();
  }
});
