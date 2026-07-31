import { defineConfig, devices } from '@playwright/test'

/**
 * 项目管理 UI E2E：打现网开发库（后端需已在 48010 运行）。
 * 数据一律通过页面点击创建，不用 API 灌数。
 *
 * Windows 上请用 npm run test:e2e（已设 PW_DISABLE_TS_ESM=1），
 * 否则 Playwright ESM loader 可能无输出挂起。
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  timeout: 120_000,
  expect: { timeout: 15_000 },
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'e2e-report' }]],
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:3003',
    trace: 'off',
    screenshot: 'only-on-failure',
    video: 'off',
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
    channel: process.env.E2E_CHANNEL || 'chrome',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'npm run dev',
    url: 'http://127.0.0.1:3003',
    reuseExistingServer: true,
    timeout: 120_000,
  },
})
