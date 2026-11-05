import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: '../../tests/e2e',
  use: { baseURL: process.env.WEB_URL || 'http://127.0.0.1:8080' },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
});
