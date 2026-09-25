import { expect, test } from '@playwright/test'

test('model settings use real guarded status and synthetic connection responses in both themes', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: '模型配置', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '模型配置' })
  await expect(dialog.getByLabel('API Key')).toBeEnabled()
  await expect(dialog).not.toContainText('配置状态读取失败')
  await expect(dialog.getByLabel('API Key')).toHaveAttribute('type', 'password')
  await page.screenshot({ path: '../artifacts/model-settings/settings-acg.png', animations: 'disabled' })
  await dialog.getByLabel('API Key').fill('synthetic-browser-credential')
  await dialog.getByRole('button', { name: '关闭', exact: true }).click()
  await page.getByRole('button', { name: '简约', exact: true }).click()
  await page.getByRole('button', { name: '模型配置', exact: true }).click()
  await expect(dialog.getByLabel('API Key')).toHaveValue('')
  await page.screenshot({ path: '../artifacts/model-settings/settings-minimal.png', animations: 'disabled' })
  await page.route('**/api/v1/model-config', async route => {
    if (route.request().method() === 'GET') return route.continue()
    expect(route.request().headers()['x-haru-csrf']).toBeTruthy()
    if (route.request().method() === 'PUT') {
      expect(route.request().postDataJSON()).toEqual({ api_key: 'synthetic-browser-credential', model: 'fixture-model' })
    }
    await route.fulfill({ json: { configured: route.request().method() === 'PUT', model: 'fixture-model', source: 'memory', csrf_token: 'fixture-token' } })
  })
  await dialog.getByLabel('API Key').fill('synthetic-browser-credential')
  await dialog.getByLabel('模型名称').fill('fixture-model')
  await dialog.getByRole('button', { name: '配置并测试连接' }).click()
  await expect(dialog.getByRole('status')).toContainText('连接测试成功')
  await expect(dialog.getByLabel('API Key')).toHaveValue('')
  expect(await page.evaluate(() => JSON.stringify([localStorage, sessionStorage]))).not.toContain('synthetic-browser-credential')
  await dialog.getByRole('button', { name: '清除配置', exact: true }).click()
  await expect(dialog.getByRole('status')).toContainText('已清除')
})
