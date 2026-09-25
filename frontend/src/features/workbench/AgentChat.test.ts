import { beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { api } from '../../api/client'
import type { AgentTask, Run } from '../../api/types'
import AgentChat from './AgentChat.vue'
import { state } from '../../state'

vi.mock('../../api/client', () => ({
  api: {
    agentStatus: vi.fn(),
    agentTasks: vi.fn(),
    createAgentTask: vi.fn(),
    replyAgent: vi.fn(),
    resumeAgent: vi.fn(),
    confirmAgent: vi.fn(),
  },
}))
const run: Run = {
  attempt: 1,
  id: 'run-one',
  kind: 'project',
  status: 'completed',
  project_ids: ['p'],
  project_names: ['模拟'],
  created_at: '2026-08-31',
  forecast_origin: '2026-08-31',
  information_cutoff: '2026-08-31',
  scenario: 'base',
  revision_ids: ['r'],
  members: [],
  steps: [],
}
const task: AgentTask = {
  mode: 'query',
  calls: 1,
  attempt: 1,
  id: 'task',
  run_id: run.id,
  question: '利润呢？',
  status: 'awaiting_reply',
  created_at: '2026-08-31',
  model: 'test-only',
  provider: 'test-only',
  clarification: '请明确期间',
  reply_token: 'token-one',
  steps: [],
}
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(api.agentStatus).mockResolvedValue({
    max_calls: 3,
    configured: true,
    provider: 'test-only',
    model: 'test-only',
  })
  vi.mocked(api.agentTasks).mockResolvedValue([])
})

it('selects an older pending task and retains its full clarification history', async () => {
  const older = {
    ...task,
    id: 'older',
    dialogue: [
      { role: 'assistant' as const, content: '确认看哪个项目？' },
      { role: 'user' as const, content: '当前范围' },
    ],
  }
  vi.mocked(api.agentTasks).mockResolvedValue([
    { ...task, id: 'newer', status: 'completed' },
    older,
  ])
  const wrapper = mount(AgentChat, { props: { run } })
  await flushPromises()
  await wrapper
    .findAll('button')
    .find((button) => button.text() === '选择此任务')!
    .trigger('click')
  expect(wrapper.text()).toContain('你的补充：当前范围')
  await wrapper.get('#agent-reply').setValue('未来12个月')
  await wrapper.findAll('form')[1]!.trigger('submit')
  await flushPromises()
  expect(api.replyAgent).toHaveBeenCalledWith('older', { token: 'token-one', reply: '未来12个月' })
  wrapper.unmount()
})

it('binds confirmation to the displayed draft and preserves conflicts for review', async () => {
  const draft: NonNullable<AgentTask['draft']> = {
    id: 'draft-one',
    token: 'approval-one',
    project_id: 'p',
    project_name: '模拟',
    phase_id: 'phase',
    phase_name: '一期',
    base_revision_id: 'r',
    base_version: 1,
    known_on: '2026-09-24',
    change: { phase_id: 'phase', field: 'price_change', value: '-0.05' },
    before: '10000',
    after: '9500',
    preview: {
      project_id: 'p',
      project_name: '模拟',
      revision_id: 'r',
      version: 1,
      scenario: 'base',
      scenario_price_percent: '0',
      scenario_cost_percent: '0',
      price_percent: '0',
      cost_percent: '0',
      future_cost_before: null,
      future_cost_after: null,
      collection_lag: 3,
      extra_collection_delay: 0,
      phases: [],
      warnings: [],
    },
  }
  vi.mocked(api.agentTasks).mockResolvedValue([
    { ...task, mode: 'change', status: 'awaiting_confirmation', draft },
  ])
  vi.mocked(api.confirmAgent).mockRejectedValue(new Error('数据已被修订'))
  const wrapper = mount(AgentChat, { props: { run } })
  await flushPromises()
  expect(api.confirmAgent).not.toHaveBeenCalled()
  await wrapper
    .findAll('button')
    .find((button) => button.text() === '确认此草稿并保存新版本')!
    .trigger('click')
  await flushPromises()
  expect(api.confirmAgent).toHaveBeenCalledExactlyOnceWith('task', {
    draft_id: 'draft-one',
    token: 'approval-one',
    project_id: 'p',
    phase_id: 'phase',
    base_revision_id: 'r',
    base_version: 1,
  })
  expect(wrapper.text()).toContain('数据已被修订')
  expect(wrapper.text()).toContain('10000 → 9500')
  wrapper.unmount()
})
it('shows unconfigured state without fabricating an answer or calling a model', async () => {
  vi.mocked(api.agentStatus).mockResolvedValue({
    max_calls: 3,
    configured: false,
    provider: 'DeepSeek',
    model: '',
  })
  const wrapper = mount(AgentChat, { props: { run } })
  await flushPromises()
  expect(wrapper.text()).toContain('DeepSeek 未配置')
  expect(wrapper.get('#agent-question').attributes('disabled')).toBeDefined()
  expect(api.createAgentTask).not.toHaveBeenCalled()
  wrapper.unmount()
})
it('loads a persisted clarification and submits its exact token once', async () => {
  vi.mocked(api.agentTasks).mockResolvedValue([task])
  vi.mocked(api.replyAgent).mockResolvedValue({ ...task, status: 'completed' })
  const wrapper = mount(AgentChat, { props: { run } })
  await flushPromises()
  expect(wrapper.text()).toContain('请明确期间')
  await wrapper.get('#agent-reply').setValue('未来12个月')
  vi.mocked(api.agentTasks).mockResolvedValue([{ ...task, status: 'completed' }])
  await wrapper.findAll('form')[1]!.trigger('submit')
  await flushPromises()
  expect(api.replyAgent).toHaveBeenCalledExactlyOnceWith('task', {
    token: 'token-one',
    reply: '未来12个月',
  })
  expect(wrapper.text()).toContain('回答已保存')
  wrapper.unmount()
})
it('ignores a late response after switching the bound run', async () => {
  let resolveOld!: (value: AgentTask[]) => void
  vi.mocked(api.agentTasks).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        resolveOld = resolve
      }),
  )
  const wrapper = mount(AgentChat, { props: { run } })
  await wrapper.setProps({ run: { ...run, id: 'run-two' } })
  await flushPromises()
  resolveOld([task])
  await flushPromises()
  expect(wrapper.text()).not.toContain('请明确期间')
  expect(wrapper.text()).toContain('run-two')
  wrapper.unmount()
})

it('ignores a stale refresh on the same run', async () => {
  let resolveOld!: (tasks: AgentTask[]) => void
  vi.mocked(api.agentTasks).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        resolveOld = resolve
      }),
  )
  const wrapper = mount(AgentChat, { props: { run } })
  vi.mocked(api.agentTasks).mockResolvedValue([{ ...task, status: 'completed' }])
  state.modelConfigurationVersion++
  await flushPromises()
  resolveOld([task])
  await flushPromises()
  expect(wrapper.find('#agent-reply').exists()).toBe(false)
  expect(wrapper.text()).toContain('回答已保存')
  wrapper.unmount()
})

it('keeps an active clarification when another window adds a newer task', async () => {
  vi.mocked(api.agentTasks).mockResolvedValue([task])
  const wrapper = mount(AgentChat, { props: { run } })
  await flushPromises()
  await wrapper.get('#agent-reply').setValue('正在补充的期间')
  vi.mocked(api.agentTasks).mockResolvedValue([
    { ...task, id: 'new-task', status: 'completed' },
    task,
  ])
  state.modelConfigurationVersion++
  await flushPromises()
  expect((wrapper.get('#agent-reply').element as HTMLTextAreaElement).value).toBe('正在补充的期间')
  wrapper.unmount()
})
