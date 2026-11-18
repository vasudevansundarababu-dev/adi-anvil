import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';

// Browser-only synthetic API replies; no identity login, remote request or provider.
const project = 'a0000000-0000-4000-8000-000000000002';
const credential = {
  id: '10000000-0000-4000-8000-000000000001',
  current_version_id: '10000000-0000-4000-8000-000000000002',
  name: 'Shared synthetic HF credential',
  provider: 'huggingface',
  revoked_at: null,
};
const metadata = JSON.parse(
  readFileSync('services/backend/src/anvil/open_weight_repositories.json', 'utf8'),
);
const catalog = {
  items: Object.entries(metadata.items).map(([id, repositories]: [string, any]) => ({
    id,
    label: repositories[0].repository,
    publisher: 'Workbook model',
    license_claim: 'Unreviewed workbook claim',
    repositories,
  })),
};
const repository = metadata.items['ow-r2-v1'][0];
const hf = {
  id: '20000000-0000-4000-8000-000000000001',
  name: 'Synthetic HF profile',
  provider: 'huggingface',
  model_id: repository.repository,
  group: 'open-weight-models',
  hub: { catalog_id: 'ow-r2-v1', repository: repository.repository, revision: repository.revision },
  credential_binding: { id: credential.id, version_id: credential.current_version_id },
  credential_present: true,
  credential_state: 'configured',
  credential_name: credential.name,
  status: 'planning_only',
  config_hash: 'a'.repeat(64),
  max_output_tokens: 4096,
  workspace_profile: true,
  profile_id: '30000000-0000-4000-8000-000000000001',
  version: 1,
  profile_row_version: 1,
  is_current: true,
  pricing_state: 'missing',
  pricing: null,
  processing_terms: null,
};
const other = {
  ...hf,
  id: '20000000-0000-4000-8000-000000000002',
  name: 'Synthetic provider profile',
  provider: 'openai',
  model_id: 'synthetic-no-live-model',
  group: 'provider-models',
  hub: null,
};

test('bulk model registration, delayed editor catalog preservation and explicit Run model versions', async ({
  page,
}) => {
  const writes: { path: string; body: any }[] = [];
  const templateWrites: string[] = [];
  const template = {
    id: 'test-template',
    template_id: 'test-kyc',
    version: 7,
    spec_sha256: 'a'.repeat(64),
  };
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.hostname !== '127.0.0.1') return route.abort();
    if (!url.pathname.startsWith('/api/v1/')) return route.continue();
    const path = url.pathname;
    if (path.includes('/generic/templates')) {
      if (route.request().method() === 'POST') templateWrites.push(path);
      return route.fulfill({
        json: {
          data: path.endsWith('/qualify')
            ? {
                receipt: {
                  status: 'blocked',
                  requirements: ['REVIEW_PRAXIS_PUBLICATION'],
                  publication_verified: false,
                  conformance: {
                    passed: false,
                    origin: 'installed_golden_qualification_missing',
                    requirements: ['independent_component_qualification_invalid_or_stale'],
                  },
                },
              }
            : route.request().method() === 'POST'
              ? template
              : [template],
        },
      });
    }
    let data: any = {
      items: [],
      next_cursor: null,
      roles: [],
      configured: false,
      can_configure: false,
    };
    if (path === '/api/v1/me')
      data = {
        id: 'synthetic-browser-user',
        name: 'Synthetic browser control',
        projects: [
          {
            id: project,
            name: 'Synthetic browser project',
            roles: ['admin'],
            workspace_access: {
              profile: 'admin',
              label: 'Admin',
              capabilities: [
                'workspace.read',
                'models.manage',
                'frameworks.manage',
                'harbor.prepare',
                'task_drafts.write',
              ],
              mapping_state: 'recorded',
            },
          },
        ],
      };
    if (path.endsWith('/workspace/benchmark')) data = { runs: [], groups: [] };
    else if (path.endsWith('/models/catalog')) {
      await new Promise((resolve) => setTimeout(resolve, 300));
      data = catalog;
    } else if (path.endsWith('/credentials'))
      data = { items: [credential], next_cursor: null, entry_available: true };
    else if (path.endsWith('/models')) data = { items: [hf, other], next_cursor: null };
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON();
      writes.push({ path, body });
      data = path.endsWith('/catalog/register') ? { items: [hf], live_available: false } : hf;
    }
    await route.fulfill({ json: { data } });
  });
  await page.goto('/workspace/' + project + '/admin');
  await page.getByRole('button', { name: 'Models & Keys', exact: true }).click();
  const group = page.getByRole('region', { name: 'Open Weight Models', exact: true });
  await group
    .getByRole('combobox', { name: 'Shared Hugging Face credential', exact: true })
    .selectOption(credential.id + ':' + credential.current_version_id);
  await group.getByText('Select repository variants and versions', { exact: false }).click();
  const table = group.getByRole('table', { name: 'Open Weight model versions' });
  await expect(table.getByRole('columnheader')).toHaveText([
    'Select',
    'Name',
    'Version',
    'Repository',
    'Terms',
  ]);
  await expect(table.getByRole('checkbox')).toHaveCount(32);
  await page.screenshot({ path: '.local/ui-open-weight-table.png' });
  await group.getByRole('button', { name: 'Select all listed versions', exact: true }).click();
  await group.getByRole('button', { name: 'Add selected model versions', exact: true }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0].body.models).toHaveLength(32);
  expect(writes[0].body.credential_id).toBe(credential.id);
  expect(writes[0].body.credential_version_id).toBe(credential.current_version_id);
  const list = page.getByRole('region', { name: 'Model profile list', exact: true });
  await list.getByRole('button', { name: 'Edit as new version', exact: true }).first().click();
  const editor = page.getByRole('region', { name: 'Model configuration editor', exact: true });
  await expect(
    editor.getByRole('combobox', { name: 'Open Weight Models catalog', exact: false }),
  ).toHaveValue('ow-r2-v1');
  await expect(editor.getByLabel('Exact Hub commit revision', { exact: false })).toHaveValue(
    repository.revision,
  );
  await editor.getByRole('button', { name: 'Save new model version', exact: true }).click();
  await expect.poll(() => writes.length).toBe(2);
  expect(writes[1].body.open_weight_catalog_id).toBe('ow-r2-v1');
  expect(writes[1].body.hub_revision).toBe(repository.revision);
  await list.getByRole('button', { name: 'Add model', exact: true }).click();
  await editor
    .getByRole('combobox', { name: 'Provider', exact: false })
    .selectOption('huggingface');
  await expect(editor.getByRole('table', { name: 'Open Weight model versions' })).toBeVisible();
  await editor.getByRole('button', { name: 'Select all listed versions', exact: true }).click();
  await editor
    .getByRole('combobox', { name: 'Credential version', exact: false })
    .selectOption(credential.id + ':' + credential.current_version_id);
  await page.screenshot({ path: '.local/ui-open-weight-create.png' });
  await editor.getByRole('button', { name: 'Save selected models with shared credential' }).click();
  await expect.poll(() => writes.length).toBe(3);
  expect(writes[2].body.models).toHaveLength(32);
  expect(writes[2].body.credential_version_id).toBe(credential.current_version_id);
  await page.goto('/workspace/' + project + '/frameworks');
  const preset = page.getByRole('region', { name: 'Execution preset configuration', exact: true });
  await preset
    .getByRole('combobox', { name: 'Model and version', exact: true })
    .selectOption(other.id);
  await preset.getByRole('button', { name: 'Add model version', exact: true }).click();
  await preset
    .getByRole('combobox', { name: 'Model group', exact: true })
    .selectOption('open-weight-models');
  await expect(preset.locator('[aria-label="Selected model versions"]')).toContainText(
    'Outside current filter',
  );
  await preset
    .getByRole('combobox', { name: 'Model and version', exact: true })
    .selectOption(hf.id);
  await preset.getByRole('button', { name: 'Add model version', exact: true }).click();
  await expect(preset.locator('[aria-label="Selected model versions"]')).toContainText(
    repository.revision,
  );
  expect(writes).toHaveLength(3);
  for (const path of ['projects', 'execution-groups']) {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/workspace/' + project + '/' + path);
    const search = page.getByRole('textbox', { name: /^Search/ });
    const button = page.getByRole('button', { name: 'Search', exact: true });
    await expect(search).toBeVisible();
    const inputBox = await search.boundingBox();
    const buttonBox = await button.boundingBox();
    expect(inputBox!.width).toBeGreaterThan(400);
    expect(
      Math.abs(inputBox!.y + inputBox!.height - buttonBox!.y - buttonBox!.height),
    ).toBeLessThan(2);
    expect(buttonBox!.x - inputBox!.x - inputBox!.width).toBeLessThan(20);
    await page.screenshot({ path: '.local/ui-' + path + '-desktop.png' });
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(search).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
    await page.screenshot({ path: '.local/ui-' + path + '-mobile.png' });
  }
  expect(errors).toEqual([]);
  await page.goto('/workspace/' + project + '/projects');
  await page.getByText('Template registration and qualification', { exact: true }).click();
  await page.getByLabel('Template specification JSON', { exact: true }).setInputFiles({
    name: 'synthetic-template.json',
    mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify({ authoring: {}, execution: {}, skills: {} })),
  });
  await page.getByRole('button', { name: 'Register exact template' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Registered template' })).toBeVisible();
  await page.getByRole('button', { name: 'Check qualification v7' }).click();
  await expect(page.getByRole('heading', { name: 'Qualification result: blocked' })).toBeVisible();
  await expect(
    page.getByText('independent_component_qualification_invalid_or_stale', { exact: true }),
  ).toBeVisible();
  expect(templateWrites).toHaveLength(2);
  expect(errors).toEqual([]);
});
