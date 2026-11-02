import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';

test('workspace profiles preserve people history and keep engineer administration restricted', async ({
  browser,
}) => {
  const project = 'a0000000-0000-4000-8000-000000000002';
  for (const username of ['admin-1', 'researcher']) {
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.goto('/');
    await page.getByRole('link', { name: 'Sign in with Keycloak' }).click();
    await page.locator('#username').fill(username);
    const password = readFileSync('.local/demo-accounts.md', 'utf8')
      .split('\n')
      .find((l) => l.startsWith('- ' + username + ':'))!
      .split('`')[1];
    await page.locator('#password').fill(password);
    await page.locator('#kc-login').click();
    await expect(page.getByRole('button', { name: 'Sign out', exact: true })).toBeVisible();
    await page.goto('/workspace/' + project + '/people');
    if (username === 'admin-1') {
      await expect(
        page.getByRole('heading', { name: 'Project people', exact: true }),
      ).toBeVisible();
      await expect(
        page.getByText('Invitation, promotion and project-access revocation', { exact: false }),
      ).toBeVisible();
      const people = await (
        await page.request.get('/api/v1/projects/' + project + '/workspace/people')
      ).json();
      await expect(page.locator('main tbody tr')).toHaveCount(people.data.items.length);
      await expect(
        page.getByRole('cell', { name: 'RL Engineer', exact: true }).first(),
      ).toBeVisible();
      await page.setViewportSize({ width: 390, height: 844 });
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
      ).toBe(true);
      await page.screenshot({
        path: 'artifacts/test-runs/modern-people-mobile.png',
        fullPage: true,
      });
    } else {
      await expect(page.getByText('researcher · RL Engineer', { exact: true })).toBeVisible();
      await expect(page.getByRole('link', { name: 'Models & keys', exact: true })).toHaveCount(0);
      await expect(page.getByRole('main').getByRole('alert')).toHaveText(
        'Administration is restricted to project Admins.',
      );
      expect(
        (await page.request.get('/api/v1/projects/' + project + '/workspace/people')).status(),
      ).toBe(403);
      await page.getByRole('link', { name: 'Tasks', exact: true }).click();
      await expect(page.getByRole('heading', { name: 'Tasks', exact: true })).toBeVisible();
    }
    await context.close();
  }
});

test('separate successor editor appends a persisted draft and keeps old versions read-only', async ({
  page,
}) => {
  const fixture = JSON.parse(
    execFileSync('services/backend/.venv/bin/python', ['tests/prepare_editor_fixture.py'], {
      encoding: 'utf8',
    }),
  );
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
  await page.goto(
    '/workspace/' +
      fixture.project_id +
      '/editor?kind=diagnostic&revision=' +
      fixture.revision_id +
      '&return_run=' +
      fixture.return_run,
  );
  await expect(page.getByRole('heading', { name: 'Review changes', exact: true })).toBeVisible();
  const threshold = page.getByLabel('Pass threshold', { exact: false });
  const previous = await threshold.inputValue();
  const changed = Number(previous) > 80 ? Number(previous) - 5 : Number(previous) + 5;
  await threshold.fill(String(changed));
  const response = page.waitForResponse(
    (r) => r.url().endsWith('/successor') && r.request().method() === 'POST',
  );
  await page.getByRole('button', { name: 'Save new draft version', exact: true }).click();
  const savedResponse = await response;
  expect(savedResponse.status()).toBe(200);
  const saved = (await savedResponse.json()).data;
  await expect(page).toHaveURL(new RegExp('revision=' + saved.revision_id));
  await page.reload();
  await expect(page.getByRole('heading', { name: /rubric · version 2/ })).toBeVisible();
  await expect(threshold).toHaveValue(String(changed));
  await page.getByRole('link', { name: 'Version 1', exact: true }).click();
  await expect(threshold).toHaveValue(previous);
  await expect(threshold).toBeDisabled();
  await expect(
    page.getByRole('button', { name: 'Save new draft version', exact: true }),
  ).toBeDisabled();
  await page.setViewportSize({ width: 320, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.screenshot({ path: 'artifacts/test-runs/modern-version-editor.png', fullPage: true });
});

test('modern diagnostic dashboard preserves exact snapshots and finalized-only output', async ({
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
  const journey = JSON.parse(readFileSync('artifacts/test-runs/journey.json', 'utf8'));
  const route = '/workspace/' + journey.project_id + '/runs?kind=diagnostic&run=' + journey.run_id;
  await page.goto(route);
  await expect(page.getByText('Reviewed mean score', { exact: true })).toBeVisible();
  await expect(page.getByText('6 scored / 6 created attempts', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Results', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'All diagnostic results', exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Inspect finalized output', exact: true }).first().click();
  await expect(
    page.getByRole('heading', { name: 'Retained finalized output', exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Task & evaluations', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Bound evaluation configuration', exact: true }),
  ).toBeVisible();
  await expect(page.locator('main pre').last()).toContainText('rubrics');
  await expect(page.locator('main pre').last()).not.toContainText('reviewer_ids');
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole('heading', { name: 'Bound evaluation configuration', exact: true }),
  ).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.screenshot({
    path: 'artifacts/test-runs/modern-diagnostic-mobile.png',
    fullPage: true,
  });
});

test('Admin modern workspace persists model profiles and keeps navigation modern-only', async ({
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
  await expect(page.getByRole('group', { name: 'Saved API key', exact: true })).toContainText(
    'No key selected for this model',
  );
  await page.getByRole('button', { name: 'Save model profile', exact: true }).click();
  // Profiles are paginated; an exact persisted profile is verified through the API, too.
  await expect(page.getByText('Profile saved to this project.', { exact: false })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Model profiles', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Add credential', exact: true }).click();
  const credentialName = 'Test-only browser credential ' + Date.now();
  // A newly saved UUID may be outside the first page. Keep the write response visible.
  const credentialListPath = '**/workspace/credentials';
  await page.route(credentialListPath, async (route) => {
    if (route.request().method() !== 'GET') return route.continue();
    const response = await route.fetch();
    const body = await response.json();
    body.data.items = body.data.items.filter(
      (item: { name: string }) => item.name !== credentialName,
    );
    await route.fulfill({ response, json: body });
  });
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
  await expect(page.getByText('Key saved securely:', { exact: false })).toBeVisible();
  const credentialRow = page.getByRole('row').filter({ hasText: credentialName });
  await credentialRow.getByRole('button', { name: 'Revoke', exact: true }).click();
  await expect(credentialRow.getByText('Revoked', { exact: true })).toBeVisible();
  await expect(credentialRow).toHaveCount(1);
  await page.unroute(credentialListPath);
  await page.getByRole('link', { name: 'Frameworks', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Semantic Kernel', exact: true })).toBeVisible();
  await expect(page.getByText('Adapter not implemented.', { exact: false }).first()).toBeVisible();
  await page.getByRole('button', { name: 'Configure Harbor', exact: true }).click();
  await page.getByLabel('Profile name', { exact: false }).fill('Browser Harbor ' + Date.now());
  await page.getByRole('button', { name: 'Save framework profile', exact: true }).click();
  await expect(page.getByText('Framework metadata saved.', { exact: false })).toBeVisible();
  await expect(
    page
      .getByRole('navigation', { name: 'Workspace navigation' })
      .getByRole('link', { name: 'Runs', exact: true }),
  ).toHaveCount(0);
  await page.goto('/workspace/' + project + '/runs');
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
  await expect(
    page.getByRole('link', { name: 'Compare classic journey', exact: false }),
  ).toHaveCount(0);
  await page.goto('/workspace/' + project + '/overview');
  await expect(
    page.getByRole('heading', { name: 'Set up your workspace', exact: true }),
  ).toBeVisible();
  await page.screenshot({ path: 'artifacts/test-runs/modern-workspace-admin.png', fullPage: true });
});
