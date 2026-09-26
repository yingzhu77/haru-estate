import { expect, test } from '@playwright/test'

test('new project, real forecast, themes, evidence, frozen portfolio and history', async ({
  page,
  request,
}) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.text().includes('Failed to resolve component')) errors.push(message.text())
  })
  const name = `浏览器验收模拟-${Date.now()}`
  const partnerName = `${name}-汇总成员`
  const partner = await request.post('/api/v1/projects', {
    headers: { 'Idempotency-Key': `portfolio-partner-${Date.now()}` },
    data: { name: partnerName, template: 'demo' },
  })
  expect(partner.ok()).toBe(true)
  await page.goto('/projects')
  await page.getByRole('textbox', { name: '新项目名称' }).fill(name)
  await page.getByText('模拟模板', { exact: true }).click()
  await page.getByRole('button', { name: '创建项目', exact: true }).click()
  await expect(page).toHaveURL(/\/data$/)
  await expect(page.getByRole('heading', { name: '数据与假设', exact: true })).toBeVisible()
  await page.getByRole('link', { name: '预测工作台', exact: true }).click()
  await page.getByRole('button', { name: '生成情景预测', exact: true }).click()
  await expect(page.getByText('本次测算已保存。', { exact: false })).toBeVisible()
  const before = await (await request.get('/api/v1/runs')).json()
  const run = before.find((r: { project_names: string[] }) => r.project_names.includes(name))
  expect(run.status).toBe('completed')
  const firstMetric = page.getByRole('button', { name: /^下月利润/ })
  await page.evaluate(() => window.scrollTo(0, 0))
  const beforeBox = await firstMetric.boundingBox()
  const beforeText = await firstMetric.innerText()
  await page.getByRole('button', { name: '简约', exact: true }).click()
  expect(await firstMetric.boundingBox()).toEqual(beforeBox)
  expect(await firstMetric.innerText()).toEqual(beforeText)
  expect((await (await request.get('/api/v1/runs')).json()).length).toBe(before.length)
  await page.screenshot({ path: '../artifacts/minimal-1440.png', fullPage: true })
  await page.getByRole('button', { name: '晴日', exact: true }).click()
  await firstMetric.click()
  await expect(page.getByRole('dialog', { name: '来源追溯' })).toBeVisible()
  await expect(page.getByText('delivery-recognition', { exact: true }).first()).toBeVisible()
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: /项目汇总/ }).click()
  const labels = page.locator('.project-checks label')
  for (const label of await labels.all()) {
    const wanted = [name, partnerName].includes((await label.innerText()).trim())
    if (await label.getByRole('checkbox').isChecked() !== wanted) await label.click()
  }
  await expect(page.getByRole('checkbox', { name, exact: true })).toBeChecked()
  await page.getByRole('button', { name: '生成项目汇总', exact: true }).click()
  await expect(page.getByText('本次测算已保存。', { exact: false })).toBeVisible()
  const total = (await (await request.get('/api/v1/runs')).json()).find(
    (r: { kind: string }) => r.kind === 'portfolio',
  )
  expect(total.members.length).toBe(2)
  expect(total.members.every((m: { status: string }) => m.status === 'completed')).toBe(true)
  await page.getByRole('button', { name: /^未来12个月利润/ }).click()
  await expect(page.getByText('汇总成员与贡献')).toBeVisible()
  await page.getByRole('button', { name: '查看项目来源' }).first().click()
  await expect(page.getByText('组成记录与规则')).toBeVisible()
  await page.keyboard.press('Escape')
  await page.setViewportSize({ width: 1920, height: 1080 })
  await page.screenshot({ path: '../artifacts/acg-1920.png', fullPage: true })
  await page.getByRole('button', { name: '简约', exact: true }).click()
  await page.screenshot({ path: '../artifacts/minimal-1920.png', fullPage: true })
  await page.goto(`/runs/${total.id}`)
  await expect(page.getByText('当次汇总成员', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByText(total.id, { exact: true })).toBeVisible()
  expect(errors).toEqual([])
})
