import { beforeEach, expect, it } from 'vitest'
import { mount, RouterLinkStub } from '@vue/test-utils'
import type { Revision } from '../../api/types'
import { state } from '../../state'
import ParameterPanel from './ParameterPanel.vue'

const revision = {
  id: 'revision-one',
  project_id: 'project-one',
  version: 1,
  known_on: '2026-08-31',
  created_at: '2026-08-31T00:00:00+00:00',
  note: '',
  data: {
    actual_closed_through: '2026-08',
    phases: [],
    assumptions: {
      opening_month: '2026-01',
      opening_cash: '0',
      monthly_overhead: '0',
      marketing_rate: '0',
      tax_rate: '0',
      down_payment_rate: '0',
      collection_lag: 0,
      expense_payment_lag: 0,
      loan_limit: '0',
      annual_interest_rate: '0',
    },
  },
} satisfies Revision

beforeEach(() => {
  state.mode = 'project'
  state.selectedProjectId = 'project-one'
  state.overrides = {
    'project-one': {
      price_change: '-0.14',
      remaining_cost_change: '-0.07',
      collection_delay: 0,
      delivery_delays: {},
    },
  }
})

it('displays clean percentage labels for binary floating-point fractions', () => {
  const wrapper = mount(ParameterPanel, {
    props: {
      revision,
      scenario: 'base',
      loading: false,
      busy: false,
      disabled: false,
      selectedCount: 1,
    },
    global: {
      stubs: {
        RouterLink: RouterLinkStub,
        ScenarioPreview: true,
        'el-button': true,
        'el-checkbox': true,
        'el-checkbox-group': true,
        'el-icon': true,
        'el-input-number': true,
        'el-skeleton': true,
        'el-slider': true,
      },
    },
  })

  expect(wrapper.get('label[for="price-change"]').text()).toBe('未售价格变化 -14%')
  expect(wrapper.get('label[for="cost-change"]').text()).toBe('剩余成本变化 -7%')
  expect(wrapper.text()).not.toContain('-14.000000000000002%')
  expect(wrapper.text()).not.toContain('-7.000000000000001%')
  wrapper.unmount()
})
