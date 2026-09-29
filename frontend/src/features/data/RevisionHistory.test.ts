import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ElAlert, ElOption, ElSelect, ElTable, ElTableColumn } from 'element-plus'
import { api } from '../../api/client'
import type { Revision, RevisionPage } from '../../api/types'
import RevisionHistory from './RevisionHistory.vue'

vi.mock('../../api/client', () => ({ api: { revisions: vi.fn(), compareRevisions: vi.fn(), input: vi.fn() } }))
const button = {
  props: ['disabled'],
  emits: ['click'],
  template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
}
function record(project: string, version: number) {
  return {
    id: `${project}-${version}`,
    project_id: project,
    version,
    known_on: '2026-08-31',
    created_at: '2026-09-01',
    note: '模拟版本',
  }
}
function page(project: string): RevisionPage {
  return { items: [record(project, 2), record(project, 1)], total: 12, offset: 0, limit: 10 }
}
function revision(id: string, version: number): Revision {
  return {
    id,
    project_id: 'a',
    version,
    known_on: '2026-09-30',
    created_at: '2026-09-30T00:00:00+00:00',
    note: '模拟版本',
    data: { actual_closed_through: '2026-08', phases: [{ id: 'phase-2', name: '二期住宅' }] },
  } as Revision
}
let wrapper: VueWrapper
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.revisions).mockImplementation(async (id) => page(id))
  vi.mocked(api.input).mockImplementation(async (_projectId, id) =>
    revision(id ?? 'a-2', id === 'a-1' ? 1 : 2),
  )
})
afterEach(() => wrapper?.unmount())
function open() {
  wrapper = mount(RevisionHistory, {
    props: { projectId: 'a', revisionId: 'a-2' },
    global: {
      components: { ElAlert, ElOption, ElSelect, ElTable, ElTableColumn },
      directives: { loading: {} },
      stubs: { ElButton: button },
    },
  })
}

it('requests revision pages and compares the selected immutable IDs', async () => {
  vi.mocked(api.compareRevisions).mockResolvedValue({
    project_id: 'a',
    left_id: 'a-1',
    right_id: 'a-2',
    changes: [{ path: 'data/phases/phase-2/delivery_month', before: '2027-06', after: '2027-09', kind: 'changed' }],
  })
  open()
  await flushPromises()
  await wrapper
    .findAll('button')
    .find((item) => item.text() === '查看输入差异')!
    .trigger('click')
  await flushPromises()
  expect(api.compareRevisions).toHaveBeenCalledWith('a', 'a-1', 'a-2')
  expect(api.input).toHaveBeenCalledWith('a', 'a-1')
  expect(wrapper.findAllComponents({ name: 'ElTable' })[1]!.props('data')[0].after).toBe('2027-09')
  expect(wrapper.text()).toContain('二期住宅（分期）')
  expect(wrapper.text()).toContain('交付计划延后 3 个月')
  await wrapper
    .findAll('button')
    .find((item) => item.text() === '下一页版本')!
    .trigger('click')
  await flushPromises()
  expect(api.revisions).toHaveBeenLastCalledWith('a', 10, 10)
})

it('discards delayed old-project results and clears old comparison selections', async () => {
  let resolve!: (value: RevisionPage) => void
  vi.mocked(api.revisions).mockImplementationOnce(
    () =>
      new Promise((yes) => {
        resolve = yes
      }),
  )
  open()
  await wrapper.setProps({ projectId: 'b', revisionId: 'b-2' })
  await flushPromises()
  resolve(page('a'))
  await flushPromises()
  expect(wrapper.findComponent({ name: 'ElTable' }).props('data')[0].project_id).toBe('b')
  expect(wrapper.findAllComponents(ElSelect)[0]!.props('modelValue')).toBe('b-1')
})
