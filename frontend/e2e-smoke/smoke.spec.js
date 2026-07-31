import { test, expect } from '@playwright/test'

test('smoke open login', async ({ page }) => {
  await page.goto('http://127.0.0.1:3003/login')
  await expect(page.getByTestId('login-submit')).toBeVisible()
})
