import { test, expect, Page } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { randomUUID } from 'node:crypto';

const metadataPath = process.env.ANVIL_ENVIRONMENT_PREVIEW_METADATA;
const accessPath = process.env.ANVIL_ENVIRONMENT_TEST_ACCESS;
test.skip(
  !metadataPath || !accessPath,
  'Requires an explicitly supplied owned local environment preview and test-only sign-in fixture.',
);

function fixture() {
  const info = JSON.parse(fs.readFileSync(metadataPath!, 'utf8'));
  const access = JSON.parse(fs.readFileSync(accessPath!, 'utf8'));
  if (
    access.kind !== 'synthetic-browser-test-accounts' ||
    access.provider_calls !== 0 ||
    Object.keys(access).some((k) => !['kind', 'provider_calls', 'identities'].includes(k))
  )
    throw new Error(
      'Narrow synthetic browser fixture required; runtime configuration is forbidden',
    );
  if (info.deployment || info.provider_calls !== 0 || !info.url.startsWith('http://127.0.0.1:'))
    throw new Error('Local paid-off preview required');
  return { info, access };
}

async function signIn(page: Page, identity: 'admin-1' | 'rl-engineer') {
  const { info, access } = fixture();
  await expect
    .poll(
      async () => {
        try {
          return (
            await page.request.get(
              `http://127.0.0.1:${info.oidc_port}/realms/anvil/.well-known/openid-configuration`,
            )
          ).status();
        } catch {
          return 0;
        }
      },
      { timeout: 30000 },
    )
    .toBe(200);
  await page.goto(info.url);
  await page.getByRole('link', { name: 'Sign in with Keycloak' }).click();
  await page.getByLabel('Username').fill(identity);
  await page.getByLabel('Password', { exact: true }).fill(access.identities[identity].password);
  await page.getByRole('button', { name: 'Sign In', exact: true }).click();
  await expect(page.getByRole('navigation', { name: 'Workspace navigation' })).toBeVisible();
  await page.goto(info.url);
  await expect(
    page.getByRole('heading', { name: 'Environments', exact: true }).last(),
  ).toBeVisible();
}

test('stored six-environment OpenEnv Run exposes honest gaps, retained evidence and real PDF', async ({
  page,
}, testInfo) => {
  test.setTimeout(240000);
  const { info } = fixture();
  test.skip(!info.dashboard_url, 'Requires the integrated successor preview');
  await signIn(page, 'admin-1');
  const endpoint = `/api/v1/projects/${info.project}/workspace/benchmark/runs/${info.run_id}`;
  await expect
    .poll(
      async () => {
        const response = await page.request.get(endpoint);
        return response.ok() ? (await response.json()).data.run.state : 'unavailable';
      },
      { timeout: 180000 },
    )
    .toBe('completed');
  const result = (await (await page.request.get(endpoint)).json()).data;
  expect(result.cells).toHaveLength(12);
  expect(result.run.report_review.ready).toBe(true);
  expect(result.selected_cell.capture.provider_calls).toBe(0);
  expect(result.selected_cell.assessment.earned_points).toBe(null);
  expect(result.selected_cell.capture.openenv_adapter.version).toBe('0.12.0');
  await page.goto(info.dashboard_url);
  const dashboard = page.getByRole('region', { name: 'Benchmark dashboard' });
  await expect(dashboard.getByRole('button', { name: 'Export PDF', exact: true })).toBeEnabled();
  for (const name of [
    'Overview',
    'Evaluations',
    'Tasks & rubrics',
    'Failure modes',
    'Safety',
    'Remediation',
    'Report preview',
  ]) {
    await dashboard.getByRole('button', { name, exact: true }).click();
    await expect(dashboard.getByRole('button', { name: 'Export PDF', exact: true })).toBeEnabled();
    await page.screenshot({
      path: testInfo.outputPath(name.replaceAll(/[^a-zA-Z]/g, '-') + '.png'),
      fullPage: true,
    });
  }
  await dashboard
    .getByText('Environment attempts, retained evidence and retry', { exact: true })
    .click();
  const receiptDownload = page.waitForEvent('download');
  await dashboard
    .getByRole('button', { name: 'Download attempt evidence', exact: true })
    .first()
    .click();
  const receipt = await receiptDownload;
  const receiptFile = testInfo.outputPath('actual-attempt-evidence.json');
  await receipt.saveAs(receiptFile);
  expect(JSON.parse(fs.readFileSync(receiptFile, 'utf8')).content.provider_calls).toBe(0);
  const downloading = page.waitForEvent('download');
  await dashboard.getByRole('button', { name: 'Export PDF', exact: true }).click();
  const pdf = await downloading;
  const pdfFile = testInfo.outputPath('six-environment-report.pdf');
  await pdf.saveAs(pdfFile);
  expect(fs.readFileSync(pdfFile).subarray(0, 5).toString()).toBe('%PDF-');
});

test('all six materialized environments expose real tools files reset and evidence', async ({
  page,
}, testInfo) => {
  test.setTimeout(240000);
  const { info } = fixture();
  const matrix = JSON.parse(
    fs.readFileSync(path.join(info.root, 'reference-validation.json'), 'utf8'),
  );
  await signIn(page, 'admin-1');
  const library = page
    .getByRole('table')
    .filter({ has: page.getByRole('columnheader', { name: 'Template / scenario', exact: true }) });
  await expect.poll(() => library.getByRole('row').count()).toBeGreaterThanOrEqual(31);
  await page.screenshot({
    path: testInfo.outputPath('six-environment-library-viewport.png'),
    fullPage: false,
  });
  await page.screenshot({
    path: testInfo.outputPath('six-environment-library.png'),
    fullPage: true,
  });
  const operations: Record<string, string> = {
    'BOD-FIN': 'save_analysis',
    'MKT-PHONE': 'create_campaign',
    'MKT-LOCALE': 'render_variant',
    'BNK-KYC': 'request_information',
    'BNK-KYB': 'ownership_paths',
    'BNK-AML': 'record_step',
  };
  for (const template of Object.keys(operations)) {
    const row = matrix.find((r: { template: string }) => r.template === template);
    await page
      .getByRole('button', { name: `Open version ${row.environment_id.slice(0, 8)}`, exact: true })
      .click();
    const register = page.getByRole('button', { name: 'Register local version', exact: true });
    if (await register.isEnabled()) {
      await register.click();
      await expect(page.getByRole('status')).toContainText('Registered local reference');
    }
    await page.getByRole('button', { name: 'Open isolated local instance', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Live component workspace' })).toBeVisible();
    await page
      .getByLabel('Environment operation', { exact: true })
      .selectOption(operations[template]);
    await page.getByRole('button', { name: 'Execute local tool', exact: true }).click();
    await expect(page.getByText(/Ordered tool events · 1 visible/)).toBeVisible();
    const downloading = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Export trusted evidence', exact: true }).click();
    const downloaded = await downloading;
    const target = testInfo.outputPath(`${template}-actual-evidence.json`);
    await downloaded.saveAs(target);
    const captured = JSON.parse(fs.readFileSync(target, 'utf8'));
    expect(captured.content.provider_calls).toBe(0);
    expect(captured.content.model_performance).toBe(false);
    expect(captured.content.events.at(-1).operation).toBe(operations[template]);
    expect(captured.content.events.at(-1).result.status).toBe('ok');
    await page.getByRole('button', { name: 'Reset to pinned data', exact: true }).click();
    await expect(page.getByRole('status')).toContainText('Restored the exact pinned');
    await page.getByRole('button', { name: 'Files', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Actual files' })).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath(`${template}-actual-workspace.png`),
      fullPage: true,
    });
    await page.getByRole('button', { name: 'Close instance', exact: true }).click();
    await expect(page.getByRole('status')).toContainText('Instance closed');
  }
});

test('RL Engineer saves and executes all six worlds from existing execution groups UI without approval', async ({
  page,
}) => {
  test.setTimeout(240000);
  const { info } = fixture();
  test.skip(!info.dashboard_url, 'Requires integrated preview');
  await signIn(page, 'rl-engineer');
  await page.getByRole('link', { name: 'Execution groups', exact: true }).click();
  const form = page
    .getByRole('heading', { name: 'Environment-backed execution group', exact: true })
    .locator('..');
  await expect(form.getByRole('button', { name: 'Save execution group and Run' })).toBeEnabled();
  await form.locator('input[name="name"]').fill('Browser-created six-world Engineer rehearsal');
  await form.locator('select[name="harness"]').selectOption('openenv-0.12-local-v1');
  await form.locator('input[name="empty"]').check();
  expect(await form.locator('input[name="environment"]').count()).toBeGreaterThanOrEqual(6);
  const versions = JSON.parse(
    fs.readFileSync(path.join(info.root, 'reference-validation.json'), 'utf8'),
  );
  for (const template of ['BOD-FIN', 'MKT-PHONE', 'MKT-LOCALE', 'BNK-KYC', 'BNK-KYB', 'BNK-AML']) {
    const version = versions.find((v: any) => v.template === template);
    await form.locator(`input[name="environment"][value="${version.environment_id}"]`).check();
  }
  await form.getByRole('button', { name: 'Save execution group and Run' }).click();
  await page.waitForURL(/benchmark_run=/, { timeout: 15000 }).catch(async (error) => {
    throw new Error(
      String(error) +
        ' Visible errors: ' +
        JSON.stringify(await page.getByRole('alert').allTextContents()),
    );
  });
  const run = new URL(page.url()).searchParams.get('benchmark_run');
  const endpoint = `/api/v1/projects/${info.project}/workspace/benchmark/runs/${run}`;
  await expect
    .poll(
      async () => {
        const response = await page.request.get(endpoint);
        return response.ok() ? (await response.json()).data.run.state : 'unavailable';
      },
      { timeout: 180000 },
    )
    .toBe('completed');
  const data = (await (await page.request.get(endpoint)).json()).data;
  expect(data.cells).toHaveLength(12);
  expect(data.run.report_review.ready).toBe(false);
  expect(data.selected_cell.capture.provider_calls).toBe(0);
  await page.reload();
  await expect(page.getByRole('button', { name: 'Export PDF', exact: true })).toBeDisabled();
});

test('existing fictional benchmark still produces actual deterministic policy findings and export', async ({
  page,
}, testInfo) => {
  test.setTimeout(180000);
  const { info } = fixture();
  test.skip(!info.dashboard_url, 'Requires integrated preview');
  await signIn(page, 'admin-1');
  const base = `/api/v1/projects/${info.project}/workspace/benchmark`;
  const csrf = (await page.context().cookies()).find((c) => c.name === 'anvil_csrf')?.value;
  if (!csrf) throw new Error('Real synthetic sign-in CSRF cookie required');
  const commandHeaders = () => ({
    'idempotency-key': randomUUID(),
    origin: new URL(info.url).origin,
    'x-csrf-token': csrf,
  });
  const catalog = (await (await page.request.get(base)).json()).data;
  const group = catalog.groups.find((g: any) => g.id === info.task_group_id);
  const configured = await page.request.post(
    base + `/groups/${group.id}/sample-verifiers?adapter=zen`,
    { headers: commandHeaders() },
  );
  expect(configured.ok(), await configured.text()).toBe(true);
  const planResponse = await page.request.post(base + '/plans', {
    headers: commandHeaders(),
    data: {
      name: 'Integrated preview · fictional policy and safety regression',
      task_group_id: group.id,
      task_ids: group.tasks.map((t: any) => t.task_id),
      models: catalog.models.map((m: any) => m.id),
      environment_ids: group.environments.map((e: any) => e.id),
      method_ids: ['task-rubric-v1', 'safety-observed-v1'],
      repetitions: 1,
    },
  });
  expect(planResponse.ok()).toBe(true);
  const plan = (await planResponse.json()).data;
  const started = await page.request.post(base + '/runs', {
    headers: commandHeaders(),
    data: { plan_id: plan.id, expected_plan_sha256: plan.snapshot_sha256 },
  });
  expect(started.ok()).toBe(true);
  const run = (await started.json()).data;
  await expect
    .poll(
      async () => (await (await page.request.get(base + '/runs/' + run.id)).json()).data.run.state,
      { timeout: 90000 },
    )
    .toBe('completed');
  const result = (await (await page.request.get(base + '/runs/' + run.id)).json()).data;
  expect(result.cells).toHaveLength(18);
  expect(result.run.provider_calls).toBe(0);
  expect(result.failures.policy_findings.some((f: any) => f.outcome === 'fail')).toBe(true);
  const url = info.dashboard_url.replace(info.run_id, run.id);
  fs.writeFileSync(
    testInfo.outputPath('fictional-policy-run.json'),
    JSON.stringify(
      { url, run_id: run.id, provider_calls: 0, result_sha256: result.run.result_sha256 },
      null,
      2,
    ),
  );
  await page.goto(url);
  await page.getByRole('button', { name: 'Safety', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Export PDF', exact: true })).toBeEnabled();
  await page.screenshot({ path: testInfo.outputPath('actual-policy-safety.png'), fullPage: true });
  const downloading = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export PDF', exact: true }).click();
  const downloaded = await downloading;
  await downloaded.saveAs(testInfo.outputPath('fictional-policy-safety-report.pdf'));
});

test('RL Engineer can automatically build validate and register without another approval queue', async ({
  page,
}) => {
  await signIn(page, 'rl-engineer');
  await page.getByLabel('Environment template', { exact: true }).selectOption('BNK-KYC');
  await page.getByLabel('Environment scenario', { exact: true }).selectOption('complete');
  await page
    .getByRole('textbox', { name: 'Name', exact: true })
    .fill('Browser-created KYC local reference');
  await page
    .getByRole('button', { name: 'Build and validate local environment', exact: true })
    .click();
  await expect(page.getByRole('status')).toContainText('Built locally');
  await page.getByRole('button', { name: 'Register local version', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Registered local reference');
  await expect(
    page.getByText('Cloud and authentic Task readiness are separate.', { exact: false }),
  ).toBeVisible();
});
