import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: 'tests/e2e',
  // Retired classic UI journeys remain in Git history; the shipped app is modern-only.
  testIgnore: [
    '**/factory.spec.ts',
    '**/harbor.spec.ts',
    '**/journey.spec.ts',
    '**/marketing.spec.ts',
    '**/task-import.spec.ts',
    '**/wizard.spec.ts',
  ],
  timeout: 180000,
  workers: 1,
  reporter: [['list'], ['json', { outputFile: 'artifacts/test-runs/playwright.json' }]],
  use: {
    baseURL: 'http://127.0.0.1:3202',
    ...(process.env.CI ? {} : { channel: 'chrome' }),
    headless: true,
    screenshot: 'only-on-failure',
    trace: 'off',
  },
  outputDir: 'artifacts/test-runs/browser',
});
