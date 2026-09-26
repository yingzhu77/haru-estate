import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount, type VueWrapper } from '@vue/test-utils'
import { nextTick } from 'vue'
import { api } from '../../api/client'
import type { Dataset, ImportPreview, Project, Revision } from '../../api/types'
import { state } from '../../state'
import { cloneData, draftBases } from './editor'
import DataView from './DataView.vue'

vi.mock('../../api/client', () => ({
  api: {
    input: vi.fn(),
    revise: vi.fn(),
    projects: vi.fn(),
    previewImport: vi.fn(),
    confirmImport: vi.fn(),
  },
}))
vi.mock('vue-router', () => ({ onBeforeRouteLeave: vi.fn() }))
vi.mock('element-plus/es/components/message/index', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn(), error: vi.fn() },
}))
vi.mock('element-plus/es/components/message-box/index', () => ({
  ElMessageBox: { confirm: vi.fn() },
}))

const button = {
  props: { loading: Boolean, disabled: Boolean },
  emits: ['click'],
  template: '<button :disabled="loading || disabled" @click="$emit(\'click\')"><slot /></button>',
}
const alert = {
  props: { title: String },
  template: '<div role="alert">{{ title }}</div>',
}
const dataset: Dataset = {
  actual_closed_through: '2026-08',
  phases: [],
  contracts: [],
  costs: [],
  actuals: [],
  assumptions: {
    opening_month: '2026-01',
    opening_cash: '0',
    monthly_overhead: '50000',
    marketing_rate: '0.02',
    tax_rate: '0.03',
    down_payment_rate: '0.3',
    collection_lag: 3,
    expense_payment_lag: 0,
    loan_limit: '20000000',
    annual_interest_rate: '0.05',
    loan_draws: [],
    loan_repayments: [],
  },
}
function revision(projectId: string, version = 1, data = dataset): Revision {
  return {
    id: projectId + '-r' + version,
    project_id: projectId,
    version,
    known_on: '2026-08-31',
    created_at: '2026-09-01',
    note: '模拟输入',
    data: cloneData(data),
  }
}
function project(id: string): Project {
  return {
    id,
    name: id,
    archived: false,
    version: 1,
    revision_id: id + '-r1',
    created_at: '2026-01-01',
  }
}
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: Error) => void
  const promise = new Promise<T>((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}
let wrapper: VueWrapper
async function open() {
  wrapper = shallowMount(DataView, {
    global: {
      renderStubDefaultSlot: true,
      stubs: {
        ElButton: button,
        ElAlert: alert,
        ElInput: true,
        ElTag: true,
        ElEmpty: true,
        ElSkeleton: true,
        ElTable: { template: '<div />' },
        ElTableColumn: true,
        RouterLink: true,
        DatasetEditor: true,
      },
    },
  })
  await flushPromises()
}
function findButton(text: string) {
  const found = wrapper.findAll('button').find((item) => item.text() === text)
  if (!found) throw new Error('Button missing: ' + text)
  return found
}
async function previewCsv(value: ImportPreview) {
  vi.mocked(api.previewImport).mockResolvedValue(value)
  const input = wrapper.get('input[type=file]')
  Object.defineProperty(input.element, 'files', {
    configurable: true,
    value: [new File(['id,phase_id,month,known_on,metric,amount'], 'input.csv')],
  })
  await input.trigger('change')
  await flushPromises()
}
beforeEach(() => {
  vi.clearAllMocks()
  state.projects = [project('p1'), project('p2')]
  state.selectedProjectId = 'p1'
  state.selectedProjectIds = ['p1', 'p2']
  state.drafts = {}
  for (const id of Object.keys(draftBases)) delete draftBases[id]
  vi.mocked(api.input).mockImplementation(async (id) => revision(id))
  vi.mocked(api.projects).mockResolvedValue(state.projects)
})
afterEach(() => {
  wrapper?.unmount()
})

describe('project input revision interactions', () => {
  it('keeps a late save response bound to its submitted project after switching', async () => {
    await open()
    const pending = deferred<Revision>()
    vi.mocked(api.revise).mockReturnValue(pending.promise)
    state.drafts.p1 = { ...state.drafts.p1, actual_closed_through: '2026-07' }
    const submitted = cloneData(state.drafts.p1)
    await findButton('保存为新版本').trigger('click')
    state.selectedProjectId = 'p2'
    await nextTick()
    await flushPromises()
    state.drafts.p2 = { ...state.drafts.p2, actual_closed_through: '2026-06' }
    pending.resolve(revision('p1', 2, submitted))
    await flushPromises()
    expect(api.revise).toHaveBeenCalledWith(
      'p1',
      expect.objectContaining({ base_version: 1, data: submitted }),
    )
    expect(state.selectedProjectId).toBe('p2')
    expect(state.drafts.p2?.actual_closed_through).toBe('2026-06')
    expect(draftBases.p2?.version).toBe(1)
    expect(draftBases.p1?.version).toBe(2)
    expect(wrapper.text()).toContain('有未保存草稿')
  })

  it('preserves the draft and base version when the server rejects a stale revision', async () => {
    await open()
    state.drafts.p1 = { ...state.drafts.p1, actual_closed_through: '2026-07' }
    vi.mocked(api.revise).mockRejectedValue(new Error('输入版本冲突，请重新核对'))
    await findButton('保存为新版本').trigger('click')
    await flushPromises()
    expect(state.drafts.p1?.actual_closed_through).toBe('2026-07')
    expect(draftBases.p1?.version).toBe(1)
    expect(wrapper.text()).toContain('草稿已保留')
    expect(wrapper.text()).toContain('输入版本冲突')
  })

  it('does not overwrite an edit made while a save request is running', async () => {
    await open()
    const pending = deferred<Revision>()
    vi.mocked(api.revise).mockReturnValue(pending.promise)
    await findButton('保存为新版本').trigger('click')
    state.drafts.p1 = { ...state.drafts.p1, actual_closed_through: '2026-05' }
    pending.resolve(revision('p1', 2))
    await flushPromises()
    expect(state.drafts.p1?.actual_closed_through).toBe('2026-05')
    expect(draftBases.p1?.version).toBe(2)
    expect(wrapper.text()).toContain('有未保存草稿')
  })

  it('does not confirm a duplicate-only CSV preview or produce a revision', async () => {
    await open()
    await previewCsv({
      project_id: 'p1',
      base_version: 1,
      additions: [],
      duplicates: ['existing-row'],
      errors: [],
    })
    expect(wrapper.text()).toContain('existing-row')
    expect(findButton('确认导入并生成新版本').attributes('disabled')).toBeDefined()
    await findButton('确认导入并生成新版本').trigger('click')
    expect(api.confirmImport).not.toHaveBeenCalled()
  })

  it('blocks importing an old preview after the user edits the draft', async () => {
    await open()
    await previewCsv({
      project_id: 'p1',
      base_version: 1,
      duplicates: [],
      errors: [],
      additions: [
        {
          id: 'a1',
          phase_id: 'phase1',
          month: '2026-07',
          known_on: '2026-08-01',
          metric: 'collections',
          amount: '100',
          note: '',
        },
      ],
    })
    state.drafts.p1 = { ...state.drafts.p1, actual_closed_through: '2026-07' }
    await nextTick()
    expect(findButton('确认导入并生成新版本').attributes('disabled')).toBeDefined()
    expect(api.confirmImport).not.toHaveBeenCalled()
  })
})
