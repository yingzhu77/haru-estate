import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { api } from '../../api/client'
import type { EffectiveParameters } from '../../api/types'
import { state } from '../../state'
import ScenarioPreview from './ScenarioPreview.vue'

vi.mock('../../api/client', () => ({ api: { parameterPreview: vi.fn() } }))
const preview: EffectiveParameters = {
  project_id: 'a',
  project_name: '模拟项目',
  revision_id: 'r',
  version: 1,
  scenario: 'optimistic',
  scenario_price_percent: '5.00',
  scenario_cost_percent: '-3.00',
  price_percent: '15.50',
  cost_percent: '-3.00',
  future_cost_before: '10000.00',
  future_cost_after: '9700.00',
  collection_lag: 3,
  extra_collection_delay: 0,
  phases: [
    {
      id: 'p',
      name: '一期',
      original_price: '12000',
      effective_price: '13860',
      original_delivery: '2027-01',
      effective_delivery: '2027-01',
    },
  ],
  warnings: [],
}
beforeEach(() => {
  vi.useFakeTimers()
  vi.resetAllMocks()
  state.mode = 'project'
  state.selectedProjectId = 'a'
  state.overrides = {}
  state.theme = 'acg'
})
afterEach(() => vi.useRealTimers())
it('renders backend effective values and does not requery for a theme change', async () => {
  vi.mocked(api.parameterPreview).mockResolvedValue([preview])
  const wrapper = mount(ScenarioPreview, { props: { scenario: 'optimistic' } })
  await vi.advanceTimersByTimeAsync(200)
  await flushPromises()
  expect(wrapper.text()).toContain('+15.5%')
  expect(wrapper.text()).toContain('13,860')
  state.theme = 'minimal'
  await nextTick()
  await vi.advanceTimersByTimeAsync(200)
  expect(api.parameterPreview).toHaveBeenCalledTimes(1)
  wrapper.unmount()
})
it('discards the previous project response and clears values on errors', async () => {
  let resolveOld!: (value: EffectiveParameters[]) => void
  vi.mocked(api.parameterPreview).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        resolveOld = resolve
      }),
  )
  const wrapper = mount(ScenarioPreview, { props: { scenario: 'base' } })
  await vi.advanceTimersByTimeAsync(200)
  vi.mocked(api.parameterPreview).mockRejectedValueOnce(new Error('资料缺失'))
  state.selectedProjectId = 'b'
  await nextTick()
  await vi.advanceTimersByTimeAsync(200)
  resolveOld([preview])
  await flushPromises()
  expect(wrapper.text()).toContain('资料缺失')
  expect(wrapper.text()).not.toContain('13,860')
  wrapper.unmount()
})
