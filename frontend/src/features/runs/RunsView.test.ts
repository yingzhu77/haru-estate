import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount, type VueWrapper } from '@vue/test-utils'
import {
  ElAlert,
  ElOption,
  ElRadioButton,
  ElRadioGroup,
  ElSelect,
  ElTable,
  ElTableColumn,
  ElTag,
} from 'element-plus'
import { api } from '../../api/client'
import type { Run, RunPage } from '../../api/types'
import RunsView from './RunsView.vue'

vi.mock('../../api/client', () => ({ api: { runPage: vi.fn(), compare: vi.fn() } }))
const button = {
  props: ['disabled', 'loading'],
  emits: ['click'],
  template: '<button :disabled="disabled || loading" @click="$emit(\'click\')"><slot /></button>',
}
function run(id: string): Run {
  return {
    id,
    kind: 'project',
    status: 'completed',
    attempt: 1,
    created_at: '2026-09-01',
    project_ids: ['p'],
    project_names: ['模拟'],
    revision_ids: ['r'],
    forecast_origin: '2026-08-31',
    information_cutoff: '2026-08-31',
    scenario: 'base',
    members: [],
    steps: [],
    result: {
      currency: 'CNY',
      unit: '元',
      profit_basis: '模拟管理口径利润',
      rule_version: 'demo-1',
      target_months: ['2026-09'],
      months: [],
      sources: [],
      warnings: [],
      scenario_totals: {},
      summary: {
        next_month_profit: '1',
        twelve_month_profit: '1',
        lifecycle_profit: '1',
        max_funding_gap: '0',
        ending_debt: '0',
        ending_receivables: '0',
        range_low: '1',
        range_high: '1',
      },
    },
  }
}
function page(id: string, offset = 0): RunPage {
  return { items: [run(id)], total: 21, offset, limit: 20 }
}
let wrapper: VueWrapper
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.runPage).mockResolvedValue(page('first'))
})
afterEach(() => wrapper?.unmount())
function open() {
  wrapper = shallowMount(RunsView, {
    global: {
      components: {
        ElAlert,
        ElOption,
        ElRadioButton,
        ElRadioGroup,
        ElSelect,
        ElTable,
        ElTableColumn,
        ElTag,
      },
      directives: { loading: {} },
      stubs: { ElButton: button, RouterLink: true },
    },
  })
}

it('filters on the server, paginates, and retains a comparison selected on a previous page', async () => {
  open()
  await flushPromises()
  const selects = wrapper.findAllComponents(ElSelect)
  selects[1]!.vm.$emit('update:modelValue', 'first')
  await flushPromises()
  vi.mocked(api.runPage).mockResolvedValueOnce(page('second', 20))
  await wrapper
    .findAll('button')
    .find((item) => item.text() === '下一页预测')!
    .trigger('click')
  await flushPromises()
  expect(api.runPage).toHaveBeenLastCalledWith({
    projectId: undefined,
    kind: undefined,
    offset: 20,
    limit: 20,
  })
  expect(selects[1]!.props('modelValue')).toBe('first')
  selects[2]!.vm.$emit('update:modelValue', 'second')
  await flushPromises()
  vi.mocked(api.compare).mockResolvedValue({
    left_id: 'first',
    right_id: 'second',
    months: ['2026-09'],
    profit_deltas: ['1'],
    membership_changed: false,
    bridge: [
      {
        month: '2026-09',
        revenue: '2',
        cogs: '-1',
        expenses: '0',
        taxes: '0',
        interest: '0',
        profit: '1',
      },
    ],
  })
  await wrapper
    .findAll('button')
    .find((item) => item.text() === '比较共同月份')!
    .trigger('click')
  await flushPromises()
  expect(api.compare).toHaveBeenCalledWith('first', 'second')
  expect(wrapper.findAllComponents({ name: 'ElTable' })[1]!.props('data')[0].profit).toBe('1')
  selects[0]!.vm.$emit('update:modelValue', 'other-project')
  await flushPromises()
  expect(api.runPage).toHaveBeenLastCalledWith({
    projectId: 'other-project',
    kind: undefined,
    offset: 0,
    limit: 20,
  })
})

it('ignores old-page responses after a project filter changes', async () => {
  let resolve!: (value: RunPage) => void
  vi.mocked(api.runPage).mockImplementationOnce(
    () =>
      new Promise((yes) => {
        resolve = yes
      }),
  )
  open()
  wrapper.findAllComponents(ElSelect)[0]!.vm.$emit('update:modelValue', 'new-project')
  vi.mocked(api.runPage).mockResolvedValue(page('new-run'))
  await flushPromises()
  resolve(page('stale-run'))
  await flushPromises()
  expect(wrapper.findComponent({ name: 'ElTable' }).props('data')[0].id).toBe('new-run')
})
