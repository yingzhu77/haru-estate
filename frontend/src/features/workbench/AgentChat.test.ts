import { beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { api } from '../../api/client'
import type { AgentTask, Run } from '../../api/types'
import AgentChat from './AgentChat.vue'

vi.mock('../../api/client', () => ({
  api: {
    agentStatus: vi.fn(),
    agentTasks: vi.fn(),
    createAgentTask: vi.fn(),
    replyAgent: vi.fn(),
    resumeAgent: vi.fn(),
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
  calls: 1, attempt: 1,
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
