import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  workers: 1,
  timeout: 45000,
  use: {
    baseURL: process.env.HARU_E2E_URL || 'http://127.0.0.1:8080',
    viewport: { width: 1440, height: 900 },
    trace: 'retain-on-failure',
  },
  reporter: [['list'], ['html', { open: 'never' }]],
})
