import { test, expect } from '@playwright/test';
import type { Page } from '@playwright/test';
import { readFileSync } from 'node:fs';

test('prepare the interactive marketing task and keep paid launch blocked', async ({ browser }) => {
  let page: Page;
  const pages = new Map<string, Page>();
  const journey = JSON.parse(readFileSync('artifacts/test-runs/journey.json', 'utf8'));
  const users = JSON.parse(readFileSync('.local/demo-identities.json', 'utf8'));
  const base = '/api/v1/projects/' + journey.project_id;
  async function login(name: string) {
    const existing = pages.get(name);
    if (existing) {
      page = existing;
      return;
    }
    const context = await browser.newContext();
    page = await context.newPage();
    await page.goto('/');
    await page.getByRole('link', { name: 'Sign in with Keycloak' }).click();
    await page.locator('#username').fill(name);
    const password = readFileSync('.local/demo-accounts.md', 'utf8')
      .split('\n')
      .find((l) => l.startsWith('- ' + name + ':'))!
      .split('`')[1];
    await page.locator('#password').fill(password);
    await page.locator('#kc-login').click();
    await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible();
    pages.set(name, page);
  }
  async function api(path: string, body?: unknown, version?: number) {
    return page.evaluate(
      async ({ path, body, version }) => {
        const response = await fetch(path, {
          method: body === undefined ? 'GET' : 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Idempotency-Key': crypto.randomUUID(),
            'X-CSRF-Token':
              document.cookie
                .split('; ')
                .find((x) => x.startsWith('anvil_csrf='))
                ?.split('=')[1] || '',
            ...(version ? { 'If-Match': String(version) } : {}),
          },
          body: body === undefined ? undefined : JSON.stringify(body),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(JSON.stringify(data));
        return data.data;
      },
      { path: base + path, body, version },
    );
  }
  async function review(kind: string, id: string, purpose: string) {
    const row = await api('/' + kind + '/' + id);
    return api(
      '/' + kind + '/' + id + '/decisions',
      {
        purpose,
        decision: 'approve',
        rationale:
          'Synthetic UI acceptance only; no paid authorization or actual model performance.',
      },
      row.row_version,
    );
  }

  await login('data-engineer');
  await page.goto(`/p/${journey.project_id}/cases`);
  await page.getByRole('button', { name: 'Import 12-week marketing task', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Northstar Flow: 12-week marketing launch', exact: true }),
  ).toBeVisible();
  const source = (await api('/cases?q=MKT-LH-001')).find(
    (r: { content: { external_case_id: string } }) => r.content.external_case_id === 'MKT-LH-001',
  );
  let taskRow = (await api('/tasks')).find(
    (r: { content: { external_case_id: string } }) => r.content.external_case_id === 'MKT-LH-001',
  );
  let rubric = (await api('/rubrics')).find(
    (r: { current_revision_id: string }) =>
      r.current_revision_id === taskRow.content.rubric_revision_id,
  );
  rubric = await api(`/rubrics/${rubric.id}/submit`, {}, rubric.row_version);
  await login('product-owner');
  for (const [operation, destination] of [
    ['managed_evaluation', 'local_fixture'],
    ['external_processing', 'openai'],
  ]) {
    const current = await api('/cases/' + source.id);
    await api(
      `/cases/${source.id}/rights`,
      {
        operation,
        destination,
        status: 'approved',
        evidence:
          'Original synthetic data reviewed for UI qualification; paid dispatch stays blocked by real Admin gates.',
      },
      current.row_version,
    );
  }
  // D-SIMPLE: the Product Owner is the single approver.
  await login('product-owner');
  await review('rubrics', rubric.id, 'approval');
  await login('data-engineer');
  taskRow = await api(`/tasks/${taskRow.id}/submit`, {}, taskRow.row_version);
  await login('product-owner');
  taskRow = await review('tasks', taskRow.id, 'approval');
  await login('data-engineer');
  taskRow = await api(`/tasks/${taskRow.id}/publish`, {}, taskRow.row_version);

  await login('admin-1');
  await page.goto(`/p/${journey.project_id}/providers`);
  const provider = page
    .locator('article')
    .filter({ has: page.getByRole('heading', { name: 'OpenAI Responses', exact: true }) });
  await provider.getByText('Configure exact model and cost bound', { exact: true }).click();
  await expect(provider.locator('#openai-model')).toHaveValue('');
  // Explicit historical fixture selection; no current pricing or paid authority inferred.
  await provider.locator('#openai-model').fill('gpt-6-sol');
  await expect(provider.locator('#openai-pricing')).toHaveValue('');
  await expect(provider.locator('#openai-bound')).toHaveValue('');
  await expect(provider.locator('#openai-tokens')).toHaveValue('8192');
  await provider.getByRole('button', { name: 'Save configuration', exact: true }).click();
  await expect(provider.getByText(/Configuration saved/)).toBeVisible();
  const connection = (await api('/providers')).find(
    (p: { content: { provider_key: string } }) => p.content.provider_key === 'openai',
  );

  await login('researcher');
  let suite = await api('/suites', {
    title: 'UI marketing suite ' + Date.now(),
    objective_revision_id: journey.objective.current_revision_id,
    task_revision_ids: [taskRow.current_revision_id],
    selection_method: 'One registered marketing development task',
    exposure_note: 'Synthetic development task; no benchmark generalization',
    advisor_id: users.advisor,
    planned_source_count: 1,
  });
  suite = await api(`/suites/${suite.id}/submit`, {}, suite.row_version);
  await login('product-owner');
  suite = await review('suites', suite.id, 'approval');
  await login('researcher');
  suite = await api(`/suites/${suite.id}/freeze`, {}, suite.row_version);
  await page.goto(`/p/${journey.project_id}/protocols`);
  await page.getByRole('button', { name: 'New protocol', exact: true }).click();
  const title = 'UI interactive marketing ' + Date.now();
  await page.locator('#title').fill(title);
  await page.locator('#objective').selectOption(journey.objective.current_revision_id);
  await page.locator('#suite').selectOption(suite.current_revision_id);
  await page.locator('#mode').selectOption('marketing_interactive_v1');
  await page.locator('#connection').selectOption(connection.id);
  await page
    .locator('#comparison_policy')
    .fill(
      'One synthetic development task, thirteen responses, descriptive results only; UI test stops before paid dispatch.',
    );
  await page.getByRole('button', { name: 'Save draft', exact: true }).click();
  await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible();
  let protocol = (await api('/protocols')).find(
    (p: { content: { title: string } }) => p.content.title === title,
  );
  protocol = await api(`/protocols/${protocol.id}/submit`, {}, protocol.row_version);
  await login('product-owner');
  protocol = await review('protocols', protocol.id, 'approval');
  await login('researcher');
  await page.goto(`/p/${journey.project_id}/protocols`);
  await page
    .locator('article')
    .filter({ has: page.getByRole('heading', { name: title, exact: true }) })
    .getByRole('button', { name: 'Prepare marketing run', exact: true })
    .click();
  await expect(
    page.getByText('Run created. Open Run console to explicitly launch.', { exact: true }),
  ).toBeVisible();
  const run = (await api('/runs')).find(
    (r: { protocol_revision_id: string }) =>
      r.protocol_revision_id === protocol.current_revision_id,
  );
  await page.goto(`/p/${journey.project_id}/runs`);
  const card = page
    .locator('article')
    .filter({ has: page.getByRole('heading', { name: run.id, exact: true }) });
  await expect(card.getByText('Paid launch blocked.', { exact: true })).toBeVisible();
  await expect(
    card.getByRole('button', { name: 'Launch paid 12-week run', exact: true }),
  ).toBeDisabled();
  await expect(card.getByText('two real admin run approvals', { exact: true })).toBeVisible();
  await card
    .locator('section[aria-label="12-week marketing execution"]')
    .screenshot({ path: 'artifacts/test-runs/marketing-readiness.png' });
  expect((await api(`/runs/${run.id}/marketing`)).calls).toEqual([]);
  for (const actorPage of pages.values()) await actorPage.context().close();
});
