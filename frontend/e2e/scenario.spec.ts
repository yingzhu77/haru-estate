import { expect, test } from '@playwright/test'

test('scenario effective parameters are read-only and survive theme switches', async ({
  page,
  request,
}) => {
  await page.goto('/projects')
  await page.getByRole('textbox', { name: '新项目名称' }).fill(`情景透明模拟-${Date.now()}`)
  await page.getByText('模拟模板', { exact: true }).click()
  await page.getByRole('button', { name: '创建项目', exact: true }).click()
  await expect(page).toHaveURL(/\/data$/)
  await page.getByRole('link', { name: '预测工作台', exact: true }).click()
  const count = (await (await request.get('/api/v1/runs/page')).json()).total
  await page.getByRole('button', { name: '乐观', exact: true }).click()
  const slider = page.getByRole('slider', { name: '未售价格变化百分比' })
  await slider.focus()
  for (let i = 0; i < 10; i++) await slider.press('ArrowRight')
  const preview = page.getByRole('region', { name: '情景有效参数' })
  await expect(preview).toContainText('+15.5%')
  await expect(preview).toContainText('13,860')
  const text = await preview.innerText()
  await page.getByRole('button', { name: '简约', exact: true }).click()
  expect(await preview.innerText()).toBe(text)
  expect((await (await request.get('/api/v1/runs/page')).json()).total).toBe(count)
  await page.screenshot({
    path: '../artifacts/scenario-agent/parameters-minimal.png',
    fullPage: true,
  })
  await page.getByRole('button', { name: '晴日', exact: true }).click()
  await page.screenshot({ path: '../artifacts/scenario-agent/parameters-acg.png', fullPage: true })
})
