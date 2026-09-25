import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { api } from '../../api/client'
import ModelSettings from './ModelSettings.vue'

vi.mock('../../api/client', () => ({
  api: {
    modelConfiguration: vi.fn(),
    configureModel: vi.fn(),
    clearModel: vi.fn(),
  },
}))
const status = { configured: false, model: '', source: 'none' as const, csrf_token: 'test-token' }
let wrapper: ReturnType<typeof mount>
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(api.modelConfiguration).mockResolvedValue(status)
  wrapper = mount(ModelSettings, { attachTo: document.body, global: { plugins: [ElementPlus] } })
})
afterEach(() => {
  wrapper.unmount()
  document.body.innerHTML = ''
})
async function fill() {
  await wrapper.get('button').trigger('click')
  await flushPromises()
  await wrapper.get('#model-api-key').setValue('synthetic-secret')
  await wrapper.get('#model-name').setValue('test-model')
}
it('clears the key as soon as it submits and sends a guarded configuration request', async () => {
  vi.mocked(api.configureModel).mockResolvedValue({
    ...status,
    configured: true,
    model: 'test-model',
    source: 'memory',
  })
  await fill()
  await wrapper.get('form').trigger('submit')
  expect((wrapper.get('#model-api-key').element as HTMLInputElement).value).toBe('')
  await flushPromises()
  expect(api.configureModel).toHaveBeenCalledExactlyOnceWith(
    { api_key: 'synthetic-secret', model: 'test-model' },
    'test-token',
  )
  expect(wrapper.text()).toContain('连接测试成功')
  expect(JSON.stringify(localStorage)).not.toContain('synthetic-secret')
})
it('keeps errors visible without restoring the submitted key', async () => {
  vi.mocked(api.configureModel).mockRejectedValue(new Error('连接测试失败，原配置保持不变'))
  await fill()
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(wrapper.text()).toContain('原配置保持不变')
  expect((wrapper.get('#model-api-key').element as HTMLInputElement).value).toBe('')
})
it('forgets unsent credentials on close', async () => {
  await fill()
  await wrapper
    .findAll('button')
    .find((button) => button.text() === '关闭')!
    .trigger('click')
  await wrapper.get('button').trigger('click')
  await flushPromises()
  expect((wrapper.get('#model-api-key').element as HTMLInputElement).value).toBe('')
})
