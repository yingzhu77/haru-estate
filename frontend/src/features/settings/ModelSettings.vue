<script setup lang="ts">
import { ref, watch } from 'vue'
import { Setting } from '@element-plus/icons-vue'
import { api } from '../../api/client'
import { state } from '../../state'
import type { components } from '../../api/schema'

const open = ref(false)
const configuration = ref<components['schemas']['ModelConfigurationStatus'] | null>(null)
const key = ref('')
const model = ref('')
const busy = ref(false)
const loading = ref(false)
const error = ref('')
const message = ref('')
let generation = 0

watch(open, async (visible) => {
  const current = ++generation
  key.value = ''
  error.value = ''
  message.value = ''
  if (!visible) return
  loading.value = true
  try {
    const result = await api.modelConfiguration()
    if (current !== generation) return
    configuration.value = result
    model.value = result.model
  } catch {
    if (current === generation) error.value = '配置状态读取失败，请关闭弹窗后重新打开。'
  } finally {
    if (current === generation) loading.value = false
  }
})

async function save() {
  if (busy.value || !configuration.value || !key.value.trim() || !model.value.trim()) return
  busy.value = true
  error.value = ''
  message.value = ''
  const pending = api.configureModel(
    { api_key: key.value.trim(), model: model.value.trim() },
    configuration.value.csrf_token,
  )
  key.value = ''
  try {
    configuration.value = await pending
    state.modelConfigurationVersion++
    message.value = '连接测试成功，配置已在本次后端运行中生效。'
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '配置失败，请重新输入密钥后重试。'
  } finally {
    busy.value = false
  }
}

async function clear() {
  if (busy.value || !configuration.value) return
  busy.value = true
  key.value = ''
  error.value = ''
  message.value = ''
  try {
    configuration.value = await api.clearModel(configuration.value.csrf_token)
    state.modelConfigurationVersion++
    message.value = '已清除本次运行配置。表单测算、历史和来源仍可使用。'
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '清除失败，请稍后重试。'
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <button
    class="model-settings-entry"
    type="button"
    @click="open = true"
  >
    <el-icon><Setting /></el-icon><span>模型配置</span>
  </button>
  <el-dialog
    v-model="open"
    title="模型配置"
    width="min(520px, 92vw)"
    class="model-settings-dialog"
    destroy-on-close
    :close-on-click-modal="false"
  >
    <div class="model-settings-content">
      <div class="provider-card">
        <div>
          <strong>DeepSeek</strong>
          <p>为问数与变更草稿连接模型</p>
        </div>
        <el-tag :type="configuration?.configured ? 'success' : 'info'">
          {{ loading ? '读取中' : configuration?.configured ? '已配置' : '未配置' }}
        </el-tag>
      </div>
      <p class="privacy-note">
        密钥仅保存在后端内存，不写入项目文件或浏览器存储。后端重启后需重新配置。
      </p>
      <p
        v-if="configuration?.source === 'environment'"
        class="privacy-note"
      >
        当前使用启动环境配置；页面修改和清除只影响本次运行，重启仍会读取原环境变量。
      </p>
      <form
        id="model-settings-form"
        autocomplete="off"
        @submit.prevent="save"
      >
        <label for="model-api-key">API Key</label>
        <el-input
          id="model-api-key"
          v-model="key"
          type="password"
          autocomplete="new-password"
          :maxlength="512"
          :disabled="busy || loading"
          placeholder="输入你的 DeepSeek API Key"
        />
        <p class="field-help">
          提交或关闭弹窗即清空输入框；已保存的密钥不会回显。
        </p>
        <label for="model-name">模型名称</label>
        <el-input
          id="model-name"
          v-model="model"
          :maxlength="100"
          :disabled="busy || loading"
          placeholder="填写账户可用的模型标识"
        />
        <p class="field-help">
          连接测试会向 DeepSeek 发送一次模拟问题，可能产生少量费用。
        </p>
      </form>
      <p
        v-if="error"
        role="alert"
        class="configuration-error"
      >
        {{ error }}
      </p>
      <p
        v-if="message"
        role="status"
        class="configuration-success"
      >
        {{ message }}
      </p>
      <p class="field-help">
        请求仅由后端发往 DeepSeek 官方接口。请勿在问数聊天中粘贴密钥。
      </p>
    </div>
    <template #footer>
      <div class="configuration-actions">
        <el-button
          :disabled="busy || loading || !configuration?.configured"
          @click="clear"
        >
          清除配置
        </el-button>
        <el-button @click="open = false">
          关闭
        </el-button>
        <el-button
          type="primary"
          form="model-settings-form"
          native-type="submit"
          :loading="busy"
          :disabled="loading || !configuration || !key.trim() || !model.trim()"
        >
          配置并测试连接
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.model-settings-entry {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 36px;
  padding: 6px 12px;
  border: 1px solid currentColor;
  border-radius: 18px;
  color: inherit;
  background: transparent;
  font: inherit;
  cursor: pointer;
  white-space: nowrap;
}
.model-settings-entry:focus-visible {
  outline: 2px solid currentColor;
  outline-offset: 3px;
}
.model-settings-content {
  color: inherit;
  line-height: 1.65;
}
.provider-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--soft);
}
.provider-card strong {
  font-size: 20px;
  color: var(--accent);
}
.provider-card p {
  margin: 3px 0 0;
  color: var(--muted);
}
.privacy-note {
  padding: 10px 0;
  color: var(--muted);
  font-size: 13px;
}
label {
  display: block;
  font-weight: 600;
  margin: 14px 0 7px;
}
.field-help {
  color: var(--muted);
  font-size: 12px;
  margin: 7px 0 14px;
}
.configuration-error {
  color: var(--el-color-danger);
}
.configuration-success {
  color: var(--accent);
}
.configuration-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.configuration-actions .el-button {
  margin-left: 0;
  min-height: 40px;
}
</style>
