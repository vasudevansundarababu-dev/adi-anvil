import { test, expect } from '@playwright/test';

test('application entry is modern-only and legacy task bookmarks redirect', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveURL(/\/workspace$/);
  await expect(page.getByRole('heading', { name: 'One workspace for evaluation' })).toBeVisible();
  await expect(page.getByRole('link', { name: /classic/i })).toHaveCount(0);
  await page.goto('/p/a0000000-0000-4000-8000-000000000002/harbor');
  await expect(page).toHaveURL(/\/workspace\/a0000000-0000-4000-8000-000000000002\/tasks$/);
  await expect(page.getByRole('heading', { name: 'One workspace for evaluation' })).toBeVisible();
});
