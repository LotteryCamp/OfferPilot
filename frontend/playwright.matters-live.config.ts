import { defineConfig, devices } from '@playwright/test'

const backendTarget = process.env.API_PROXY_TARGET
if (!backendTarget) throw new Error('请先将 API_PROXY_TARGET 设置为可写的测试后端。')

const frontendUrl = 'http://127.0.0.1:5174'

export default defineConfig({
  testDir: './tests/live',
  outputDir: './test-results/matters-live',
  timeout: 75_000,
  retries: 0,
  workers: 1,
  use: {
    ...devices['Desktop Chrome'],
    baseURL: frontendUrl,
    channel: process.env.PLAYWRIGHT_CHANNEL,
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5174 --strictPort',
    url: frontendUrl,
    env: { API_PROXY_TARGET: backendTarget, VITE_LOCAL_DEMO_MATTERS: '1' },
    reuseExistingServer: false,
    timeout: 30_000,
  },
})
