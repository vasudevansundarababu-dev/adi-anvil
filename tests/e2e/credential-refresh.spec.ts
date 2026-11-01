import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { randomUUID } from 'node:crypto';

test('credential versions refresh after save, pagination, rotation and window focus without resetting the model draft', async ({
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
  const endpoint = '/api/v1/projects/' + project + '/workspace/credentials';
  let saved: {
    id: string;
    name: string;
    current_version_id: string;
    revoked_at: string | null;
  } | null = null;
  let failReads = false;
  const cursor = randomUUID();
  // Deterministic paginated metadata; create/rotate/revoke still use the real authorized API.
  await page.route('**' + endpoint + '**', async (route) => {
    if (route.request().method() !== 'GET') {
      const response = await route.fetch();
      expect(response.status()).toBe(200);
      saved = (await response.json()).data;
      await route.fulfill({ response });
    } else if (failReads) {
      await route.fulfill({
        status: 503,
        json: { error: { message: 'Test-only credential metadata interruption' } },
      });
    } else {
      const after = new URL(route.request().url()).searchParams.get('after');
      await route.fulfill({
        json: {
          data: {
            items: saved
              ? after
                ? [saved]
                : [
                    {
                      id: cursor,
                      name: 'Different provider metadata',
                      provider: 'gemini',
                      current_version_id: cursor,
                      revoked_at: null,
                    },
                  ]
              : [],
            next_cursor: saved && !after ? cursor : null,
            entry_available: true,
          },
        },
      });
    }
  });
  await page.goto('/workspace/' + project + '/models');
  await page.getByRole('button', { name: 'Add model', exact: true }).click();
  const editor = page.getByRole('region', { name: 'Model configuration editor', exact: true });
  await editor.getByLabel('Profile name', { exact: false }).fill('Keep my model draft');
  await editor
    .getByLabel('Exact model ID', { exact: false })
    .fill('test-only-credential-refresh-model');
  await editor.getByLabel('Maximum output tokens', { exact: false }).fill('2048');
  const picker = editor.getByRole('combobox', { name: 'Credential version', exact: true });
  const refresh = editor.getByRole('button', { name: 'Refresh credential versions', exact: true });
  await expect(refresh).toBeEnabled();
  await page.getByRole('button', { name: 'Add credential', exact: true }).click();
  const name = 'Test-only credential refresh ' + Date.now();
  await page.getByLabel('Credential name', { exact: false }).fill(name);
  await page.getByLabel('Credential provider', { exact: false }).selectOption('openai');
  await page
    .getByLabel('Secret value', { exact: false })
    .fill('test-only-not-live-' + randomUUID());
  await page.getByRole('button', { name: 'Save credential version', exact: true }).click();
  await expect(picker.locator('option').filter({ hasText: name })).toHaveCount(1);
  await expect(
    picker.locator('option').filter({ hasText: 'Different provider metadata' }),
  ).toHaveCount(0);
  const first = saved!.id + ':' + saved!.current_version_id;
  await picker.selectOption(first);
  async function mutate(suffix: string, body: unknown) {
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
        if (!response.ok) throw new Error('Credential mutation failed: ' + response.status);
        return (await response.json()).data;
      },
      { path: endpoint + suffix, body },
    );
  }
  // Simulate rotation from another screen/tab while this draft remains open.
  const second = await mutate('/' + saved!.id + '/versions', {
    secret: 'test-only-rotated-' + randomUUID(),
  });
  await refresh.click();
  const secondValue = second.id + ':' + second.current_version_id;
  await expect(picker.locator('option[value="' + secondValue + '"]')).toHaveCount(1);
  await expect(picker).toHaveValue(first);
  await expect(
    editor.getByRole('button', { name: 'Save model profile', exact: true }),
  ).toBeDisabled();
  await picker.selectOption(secondValue);
  failReads = true;
  await refresh.click();
  await expect(editor.getByRole('alert')).toHaveText('Test-only credential metadata interruption');
  await expect(
    editor.getByRole('button', { name: 'Save model profile', exact: true }),
  ).toBeDisabled();
  failReads = false;
  await refresh.click();
  await expect(editor.getByRole('alert')).toHaveCount(0);
  await expect(refresh).toBeEnabled();
  const third = await mutate('/' + saved!.id + '/versions', {
    secret: 'test-only-focus-rotation-' + randomUUID(),
  });
  await page.evaluate(() => window.dispatchEvent(new Event('focus')));
  const thirdValue = third.id + ':' + third.current_version_id;
  await expect(picker.locator('option[value="' + thirdValue + '"]')).toHaveCount(1);
  await expect(picker).toHaveValue(secondValue);
  await picker.selectOption(thirdValue);
  await expect(editor.getByLabel('Profile name', { exact: false })).toHaveValue(
    'Keep my model draft',
  );
  await expect(editor.getByLabel('Exact model ID', { exact: false })).toHaveValue(
    'test-only-credential-refresh-model',
  );
  await expect(editor.getByLabel('Maximum output tokens', { exact: false })).toHaveValue('2048');
  await expect(
    editor.getByRole('button', { name: 'Save model profile', exact: true }),
  ).toBeEnabled();
  await mutate('/' + saved!.id + '/revoke', {});
  await refresh.click();
  await expect(
    editor.getByText('The selected key version changed or was revoked.', { exact: false }),
  ).toBeVisible();
  await expect(
    editor.getByRole('button', { name: 'Save model profile', exact: true }),
  ).toBeDisabled();
});
