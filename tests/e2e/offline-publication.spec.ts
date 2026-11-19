import { test, expect } from '@playwright/test';

// Synthetic browser replies only: no login, Authoring, provider or approval effect.
test('offline publication staging requires a separate exact-record PO action and supports revocation', async ({
  page,
}) => {
  const project = 'a0000000-0000-4000-8000-000000000002';
  const template = {
    id: 'synthetic-template',
    template_id: 'synthetic-kyc',
    version: 8,
    spec_sha256: 'a'.repeat(64),
  };
  const record = {
    publication_status: 'published',
    template_id: template.template_id,
    version: template.version,
    published_at: '2026-01-01T00:00:00Z',
    template_sha256: template.spec_sha256,
    part_hashes: { authoring: 'b'.repeat(64), execution: 'c'.repeat(64), skills: 'd'.repeat(64) },
  };
  const subject: any = {
    id: 'synthetic-subject',
    sha256: 'e'.repeat(64),
    raw_record_sha256: 'f'.repeat(64),
    record,
    created_by: 'synthetic-po',
    created_at: '2026-01-02T00:00:00Z',
    revoked: false,
    attestation: null,
  };
  const writes: { path: string; body: any }[] = [];
  const subjects: any[] = [];
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.hostname !== '127.0.0.1') return route.abort();
    if (!url.pathname.startsWith('/api/v1/')) return route.continue();
    const path = url.pathname;
    let data: any = {
      items: [],
      next_cursor: null,
      configured: false,
      can_configure: false,
      roles: [],
    };
    if (path === '/api/v1/me')
      data = {
        id: 'synthetic-po',
        name: 'Synthetic PO',
        projects: [
          {
            id: project,
            name: 'Synthetic project',
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
    else if (path.endsWith('/workspace/benchmark')) data = { runs: [], groups: [] };
    else if (path.endsWith('/generic/templates')) data = [template];
    else if (path.endsWith('/qualify'))
      data = {
        receipt: {
          status: 'blocked',
          requirements: ['runtime_qualification_required'],
          publication_verified: false,
          publication_accepted: true,
          publication_basis: { kind: 'po_attested_offline', expires_at: '2099-01-01T12:00:00Z' },
          conformance: { passed: false, origin: 'runtime_qualification_required' },
        },
      };
    else if (path.includes('/offline-publications')) {
      if (route.request().method() === 'GET') data = { subjects };
      else {
        const body = route.request().postDataJSON();
        writes.push({ path, body });
        if (path.endsWith('/attest')) {
          subject.attestation = {
            id: 'synthetic-attestation',
            sha256: '1'.repeat(64),
            current: true,
            expires_at: body.expires_at,
            attested_by: 'synthetic-po',
            self_approved: true,
          };
          data = {
            publication_verified: false,
            origin: 'po_attested_offline',
            publication_accepted: true,
          };
        } else if (path.endsWith('/revoke')) {
          subject.revoked = true;
          subject.attestation.current = false;
          data = { revoked: true };
        } else {
          subjects.push(subject);
          data = { id: subject.id, sha256: subject.sha256 };
        }
      }
    }
    await route.fulfill({ json: { data } });
  });
  await page.goto('/workspace/' + project + '/projects');
  await page.getByText('Template registration and qualification', { exact: true }).click();
  const panel = page.getByRole('region', { name: 'Offline publication review', exact: true });
  await panel.getByLabel('Offline publication template', { exact: true }).selectOption(template.id);
  const upload = panel.getByLabel('Published offline publication record JSON', { exact: true });
  await upload.setInputFiles({
    name: 'candidate.json',
    mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify({ ...record, status: 'candidate' })),
  });
  await panel
    .getByRole('button', { name: 'Stage publication record for review', exact: true })
    .click();
  await expect(panel.getByRole('alert')).toContainText(
    'Candidate and unpublished records cannot be attested',
  );
  expect(writes).toHaveLength(0);
  await upload.setInputFiles({
    name: 'wrong-version.json',
    mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify({ ...record, version: 7 })),
  });
  await panel
    .getByRole('button', { name: 'Stage publication record for review', exact: true })
    .click();
  await expect(panel.getByRole('alert')).toContainText('external template ID and version');
  expect(writes).toHaveLength(0);
  const raw = JSON.stringify(record, null, 2);
  await upload.setInputFiles({
    name: 'published.json',
    mimeType: 'application/json',
    buffer: Buffer.from(raw),
  });
  await panel
    .getByRole('button', { name: 'Stage publication record for review', exact: true })
    .click();
  await expect(panel.getByRole('status')).toContainText('No approval was granted');
  expect(writes).toHaveLength(1);
  expect(writes[0].body).toEqual({ record_utf8: raw });
  await expect(panel.getByText(subject.raw_record_sha256, { exact: true })).toBeVisible();
  const attest = panel.getByRole('button', { name: 'Record local PO attestation', exact: true });
  await expect(attest).toBeDisabled();
  await panel
    .getByLabel('Publication attestation rationale', { exact: true })
    .fill('Synthetic reviewed publication evidence');
  await panel
    .getByLabel('Publication attestation expiry (local time)', { exact: true })
    .fill('2099-01-01T12:00');
  await expect(attest).toBeDisabled();
  await panel.getByRole('checkbox').check();
  expect(writes).toHaveLength(1);
  await attest.click();
  await expect(panel.getByRole('status')).toContainText('Local Product Owner attestation recorded');
  expect(writes[1].body.subject_sha256).toBe(subject.sha256);
  await page.getByRole('button', { name: 'Check qualification v8', exact: true }).click();
  await expect(
    page.getByText('Offline PO attestation accepted (not API verified).', { exact: false }),
  ).toBeVisible();
  await expect(panel.getByText(/Authoring API verification: no/)).toBeVisible();
  await panel
    .getByLabel('Publication revocation reason', { exact: true })
    .fill('Synthetic withdrawal of publication attestation');
  await panel.getByRole('button', { name: 'Revoke this publication record', exact: true }).click();
  await expect(panel.getByRole('status')).toContainText('Publication record revoked');
  await expect(attest).toBeDisabled();
  expect(writes).toHaveLength(3);
  expect(errors).toEqual([]);
});
