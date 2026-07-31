const { defineConfig } = require('@playwright/test')

module.exports = defineConfig({
  testDir: './e2e-smoke',
  workers: 1,
  reporter: 'list',
  timeout: 60000,
  use: {
    baseURL: 'http://127.0.0.1:3003',
    channel: 'chrome',
  },
})
