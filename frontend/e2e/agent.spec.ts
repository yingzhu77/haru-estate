import { expect, test } from '@playwright/test'

test('deterministic UI fixture: older clarification and period-filtered source navigation', async ({ page, request }) => {
  const projects = await (await request.get('/api/v1/projects')).json()
  const created = await (await request.post('/api/v1/runs', {
    headers: { 'Idempotency-Key': `agent-browser-${Date.now()}` },
    data: { project_ids: [projects[0].id] },
  })).json()
  await expect.poll(async () => (await (await request.get(`/api/v1/runs/${created.id}`)).json()).status).toBe('completed')
  const run = await (await request.get(`/api/v1/runs/${created.id}`)).json()
  let replied = false
  await page.route('**/api/v1/agent/status', route => route.fulfill({ json: {
    configured: true, provider: 'deterministic-browser-fixture', model: 'test-only', max_calls: 3,
  } }))
  const older = {
    id: 'older-fixture', run_id: run.id, mode: 'query', question: '利润呢？',
    status: 'awaiting_reply', created_at: '2026-09-24', model: 'test-only',
    provider: 'deterministic-browser-fixture', calls: 1, attempt: 1,
    clarification: '看哪个期间？', reply_token: 'older-token',
    dialogue: [{ role: 'assistant', content: '看哪个期间？' }], steps: [],
  }
  await page.route('**/api/v1/agent/tasks?**', route => route.fulfill({ json: [
    { ...older, id: 'newer-fixture', status: 'completed', question: '新任务' },
    { ...older, status: replied ? 'completed' : 'awaiting_reply', answer: replied ? {
      metric: 'profit', label: '模拟管理口径利润', amount: run.result.summary.twelve_month_profit,
      unit: '元', currency: 'CNY', period_label: '未来12个月', months: run.result.target_months,
      explanation: '测试界面来源导航', source_count: 1,
    } : null },
  ] }))
  await page.route('**/api/v1/agent/tasks/older-fixture/reply', async route => {
    expect(route.request().postDataJSON()).toEqual({ token: 'older-token', reply: '未来12个月' })
    replied = true
    await route.fulfill({ json: { ...older, status: 'completed' } })
  })
  await page.goto(`/runs/${run.id}`)
  const agent = page.getByRole('region', { name: 'AI 问数' })
  await agent.getByRole('button', { name: '选择此任务' }).click()
  await agent.locator('#agent-reply').fill('未来12个月')
  await page.getByRole('button', { name: '简约', exact: true }).click()
  await expect(agent.locator('#agent-reply')).toHaveValue('未来12个月')
  await agent.getByRole('button', { name: '补充后继续' }).click()
  const sources = page.waitForRequest(req => req.url().includes('/evidence?'))
  await agent.getByRole('button', { name: '查看绑定运行来源' }).click()
  const url = new URL((await sources).url())
  expect(url.searchParams.get('month_from')).toBe(run.result.target_months[0])
  expect(url.searchParams.get('month_to')).toBe(run.result.target_months.at(-1))
  await expect(page.getByRole('heading', { name: '来源追溯' })).toBeVisible()
  await page.screenshot({ path: '../artifacts/scenario-agent/agent-period-source.png', fullPage: true })
})
