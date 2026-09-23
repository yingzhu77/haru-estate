import { expect, test, type APIRequestContext } from '@playwright/test'
import type { Project, Revision, Run } from '../src/api/types'

async function complete(request: APIRequestContext, projectId: string, key: string): Promise<Run> {
  const response = await request.post('/api/v1/runs', {
    headers: { 'Idempotency-Key': key },
    data: { project_ids: [projectId] },
  })
  expect(response.ok()).toBeTruthy()
  const run = (await response.json()) as Run
  await expect
    .poll(async () => (await (await request.get(`/api/v1/runs/${run.id}`)).json()).status)
    .toBe('completed')
  return (await (await request.get(`/api/v1/runs/${run.id}`)).json()) as Run
}

test('lost write responses retry once, revision diff and profit bridge use real saved inputs', async ({
  page,
  request,
}) => {
  const name = `重试与差异模拟-${Date.now()}`
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  let loseCreate = true
  await page.route('**/api/v1/projects', async (route) => {
    if (route.request().method() === 'POST' && loseCreate) {
      loseCreate = false
      await route.fetch()
      await route.abort('failed')
    } else await route.continue()
  })
  await page.goto('/projects')
  await page.getByRole('textbox', { name: '新项目名称' }).fill(name)
  await page.getByText('模拟模板', { exact: true }).click()
  await page.getByRole('button', { name: '创建项目', exact: true }).click()
  await expect(page.getByRole('alert').filter({ hasText: /fetch|网络|失败/i })).toBeVisible()
  await page.getByRole('button', { name: '创建项目', exact: true }).click()
  await expect(page).toHaveURL(/\/data$/)
  const matches = ((await (await request.get('/api/v1/projects')).json()) as Project[]).filter(
    (p) => p.name === name,
  )
  expect(matches).toHaveLength(1)
  const project = matches[0]!
  const original = await complete(request, project.id, `baseline-${project.id}`)
  let loseSave = true
  await page.route(`**/api/v1/projects/${project.id}/revisions`, async (route) => {
    if (route.request().method() === 'POST' && loseSave) {
      loseSave = false
      await route.fetch()
      await route.abort('failed')
    } else await route.continue()
  })
  await page.getByLabel('修订信息获知日').fill('2026-08-31')
  await page.getByLabel('未售单价（元/㎡）').first().fill('13500')
  await page.getByRole('button', { name: '保存为新版本', exact: true }).click()
  await expect(page.getByRole('alert').filter({ hasText: '草稿已保留' })).toBeVisible()
  await page.getByRole('button', { name: '保存为新版本', exact: true }).click()
  await expect(page.getByText('已保存 · v2', { exact: false })).toBeVisible()
  expect((await (await request.get(`/api/v1/projects/${project.id}/revisions`)).json()).total).toBe(
    2,
  )
  await page.getByRole('button', { name: '查看输入差异', exact: true }).click()
  await expect(
    page.getByText('输入 / 分期计划 / phase-1 / 未售单价', { exact: true }),
  ).toBeVisible()
  await expect(page.locator('.revision-history').getByText('13500', { exact: true })).toBeVisible()
  await page.screenshot({ path: '../artifacts/hardening/revision-diff.png', fullPage: true })
  const revised = await complete(request, project.id, `changed-${project.id}`)
  expect(revised.revision_ids).not.toEqual(original.revision_ids)
  expect(await (await request.get(`/api/v1/runs/${original.id}`)).json()).toEqual(original)
  await page.getByRole('link', { name: '历史预测', exact: true }).click()
  await page
    .locator('.el-select')
    .filter({ has: page.getByRole('combobox', { name: '原预测', exact: true }) })
    .click()
  await page
    .locator(
      `[id="${await page.getByRole('combobox', { name: '原预测', exact: true }).getAttribute('aria-controls')}"]`,
    )
    .getByRole('option')
    .filter({ hasText: original.id.slice(0, 8) })
    .click()
  await page
    .locator('.el-select')
    .filter({ has: page.getByRole('combobox', { name: '对照预测', exact: true }) })
    .click()
  await page
    .locator(
      `[id="${await page.getByRole('combobox', { name: '对照预测', exact: true }).getAttribute('aria-controls')}"]`,
    )
    .getByRole('option')
    .filter({ hasText: revised.id.slice(0, 8) })
    .click()
  await page.getByRole('button', { name: '比较共同月份', exact: true }).click()
  await expect(page.getByText('共同月份合计', { exact: true })).toBeVisible()
  await expect(page.getByText('收入贡献', { exact: true })).toBeVisible()
  await page.screenshot({ path: '../artifacts/hardening/profit-bridge.png', fullPage: true })
  await page.getByRole('button', { name: '查看原预测来源', exact: true }).click()
  await expect(page.getByRole('dialog', { name: '来源追溯' })).toBeVisible()
  await page.keyboard.press('Escape')
  await page.getByRole('link', { name: '预测工作台', exact: true }).click()
  await page.getByRole('button', { name: '敏感性分析', exact: true }).first().click()
  await expect(page.getByText('资金缺口峰值', { exact: true })).toBeVisible()
  await expect
    .poll(async () => {
      const box = await page.getByRole('dialog', { name: '情景与敏感性分析' }).boundingBox()
      return box ? Math.round(box.x + box.width) : 0
    })
    .toBe(1440)
  await page.screenshot({ path: '../artifacts/hardening/sensitivity.png', fullPage: true })
  expect(errors).toEqual([])
})

test('invalid contract CSV is rejected in preview and adds no revision', async ({
  page,
  request,
}) => {
  const name = `导入校验模拟-${Date.now()}`
  await page.goto('/projects')
  await page.getByRole('textbox', { name: '新项目名称' }).fill(name)
  await page.getByText('模拟模板', { exact: true }).click()
  await page.getByRole('button', { name: '创建项目', exact: true }).click()
  await expect(page).toHaveURL(/\/data$/)
  const project = ((await (await request.get('/api/v1/projects')).json()) as Project[]).find(
    (p) => p.name === name,
  )!
  const revision = (await (
    await request.get(`/api/v1/projects/${project.id}/input`)
  ).json()) as Revision
  const phase = revision.data.phases![0]!.id
  await page.locator('input[type=file]').setInputFiles({
    name: 'invalid-contract.csv',
    mimeType: 'text/csv',
    buffer: Buffer.from(
      `id,phase_id,month,known_on,metric,amount,contract_id\ninvalid,${phase},2026-08,2026-08-31,collections,100,missing-contract\n`,
    ),
  })
  await expect(page.getByText(/实际记录关联的合同不属于对应分期/)).toBeVisible()
  await expect(
    page.getByRole('button', { name: '确认导入并生成新版本', exact: true }),
  ).toBeDisabled()
  expect(await (await request.get(`/api/v1/projects/${project.id}/input`)).json()).toEqual(revision)
})

test('history filters before paging and displays an older run on page two', async ({
  page,
  request,
}) => {
  const name = `分页模拟-${Date.now()}`
  const response = await request.post('/api/v1/projects', {
    headers: { 'Idempotency-Key': `history-project-${Date.now()}` },
    data: { name, template: 'demo' },
  })
  expect(response.ok()).toBeTruthy()
  const project = (await response.json()) as Project
  const runIds: string[] = []
  for (let index = 0; index < 21; index++) {
    const created = await request.post('/api/v1/runs', {
      headers: { 'Idempotency-Key': `history-${project.id}-${index}` },
      data: { project_ids: [project.id] },
    })
    expect(created.ok()).toBeTruthy()
    runIds.push(((await created.json()) as Run).id)
  }
  await page.goto('/runs')
  const input = page.getByRole('combobox', { name: '历史项目筛选', exact: true })
  await page.locator('.el-select').filter({ has: input }).click()
  await page
    .locator(`[id="${await input.getAttribute('aria-controls')}"]`)
    .getByRole('option')
    .filter({ hasText: name })
    .click()
  await expect(page.getByText('第 1 页 · 共 21 条', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '下一页预测', exact: true }).click()
  await expect(page.getByText('第 2 页 · 共 21 条', { exact: true })).toBeVisible()
  await expect(page.getByText(runIds[0]!, { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '下一页预测', exact: true })).toBeDisabled()
})
