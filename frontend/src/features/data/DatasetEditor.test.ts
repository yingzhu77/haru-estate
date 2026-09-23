import { describe, expect, it } from 'vitest'
import { shallowMount } from '@vue/test-utils'
import type { Dataset } from '../../api/types'
import DatasetEditor from './DatasetEditor.vue'

function dataset(): Dataset {
  return {
    actual_closed_through: '2026-08',
    phases: [
      {
        id: 'phase-1',
        name: '一期',
        area: '100',
        price: '200',
        sales_start: '2026-09',
        sales_months: 6,
        delivery_month: '2027-02',
        known_on: '2026-08-01',
      },
    ],
    contracts: [
      {
        id: 'signed-1',
        phase_id: 'phase-1',
        area: '10',
        amount: '2000',
        sale_month: '2026-08',
        known_on: '2026-08-01',
        recognized_month: null,
        collections: [{ month: '2026-08', amount: '600' }],
      },
    ],
    costs: [],
    actuals: [],
    assumptions: {
      opening_month: '2026-01',
      opening_cash: '0',
      monthly_overhead: '0',
      marketing_rate: '0',
      tax_rate: '0',
      down_payment_rate: '0.3',
      collection_lag: 3,
      expense_payment_lag: 0,
      loan_limit: '0',
      annual_interest_rate: '0',
    },
  }
}
function open(data: Dataset) {
  return shallowMount(DatasetEditor, {
    props: { modelValue: data, knownOn: '2026-08-31' },
    global: {
      renderStubDefaultSlot: true,
      stubs: {
        ElTabs: true,
        ElTabPane: true,
        ElEmpty: true,
        ElAlert: { props: { title: String }, template: '<p>{{ title }}</p>' },
        ElButton: {
          emits: ['click'],
          template: '<button @click="$emit(\'click\')"><slot /></button>',
        },
        PaymentEditor: true,
      },
    },
  })
}
describe('structured input editing', () => {
  it('does not silently replace an emptied numeric field with zero', async () => {
    const wrapper = open(dataset())
    await wrapper.get('input[aria-label="去化月数"]').setValue('')
    const next = wrapper.emitted('update:modelValue')?.[0]?.[0] as Dataset
    expect(next.phases?.[0]?.sales_months).toBeNull()
    wrapper.unmount()
  })
  it('preserves nested collection nodes and the original snapshot when editing contract amount', async () => {
    const data = dataset()
    const wrapper = open(data)
    await wrapper.get('input[aria-label="签约金额（元）"]').setValue('2200')
    const next = wrapper.emitted('update:modelValue')?.[0]?.[0] as Dataset
    expect(next.contracts?.[0]?.amount).toBe('2200')
    expect(next.contracts?.[0]?.collections).toEqual([{ month: '2026-08', amount: '600' }])
    expect(next.contracts?.[0]?.recognized_month).toBeNull()
    expect(data.contracts?.[0]?.amount).toBe('2000')
    wrapper.unmount()
  })
  it('prevents removing a phase that still has referenced records', async () => {
    const wrapper = open(dataset())
    const remove = wrapper.findAll('button').find((button) => button.text() === '移除草稿记录')
    await remove?.trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    expect(wrapper.text()).toContain('仍被合同、成本或实际记录引用')
    wrapper.unmount()
  })
})
