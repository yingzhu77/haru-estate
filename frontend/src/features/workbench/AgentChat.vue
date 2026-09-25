<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { api } from '../../api/client'
import type { AgentStatus, AgentTask, Run } from '../../api/types'
import { showEvidence, state } from '../../state'

const props = defineProps<{ run: Run | null }>()
const emit = defineEmits<{ confirmed: [] }>()
const status = ref<AgentStatus | null>(null)
const tasks = ref<AgentTask[]>([])
const selectedId = ref('')
const offset = ref(0)
const question = ref('')
const mode = ref<'query' | 'change'>('query')
const knownOn = ref(new Date().toLocaleDateString('en-CA'))
const reply = ref('')
const error = ref('')
const busy = ref(false)
let generation = 0
let timer: ReturnType<typeof setTimeout> | undefined
const current = computed(
  () => tasks.value.find((task) => task.id === selectedId.value) ?? tasks.value[0],
)
watch(
  () => current.value?.id,
  () => {
    reply.value = ''
  },
)
const enabled = computed(() => status.value?.configured && props.run?.status === 'completed')
const labels: Record<AgentTask['status'], string> = {
  queued: '已保存，等待处理',
  running: '正在理解问题',
  awaiting_reply: '需要你补充',
  awaiting_confirmation: '草稿待你确认',
  completed: '回答已保存',
  failed: '处理失败',
  interrupted: '服务中断，可继续',
}
async function load(token: number, runId?: string) {
  try {
    const [configuration, saved] = await Promise.all([
      api.agentStatus(),
      runId ? api.agentTasks(runId, offset.value) : Promise.resolve([]),
    ])
    if (generation !== token) return
    status.value = configuration
    tasks.value = saved
    if (saved.some((task) => ['queued', 'running'].includes(task.status))) {
      timer = setTimeout(() => void load(token, runId), 1200)
    }
  } catch (cause) {
    if (generation === token)
      error.value = cause instanceof Error ? cause.message : '问数状态读取失败'
  }
}
watch(
  () => props.run?.id,
  () => {
    ++generation
    clearTimeout(timer)
    tasks.value = []
    selectedId.value = ''
    offset.value = 0
    mode.value = 'query'
    question.value = ''
    reply.value = ''
    error.value = ''
    busy.value = false
    void load(generation, props.run?.id)
  },
  { immediate: true },
)
onBeforeUnmount(() => {
  ++generation
  clearTimeout(timer)
})
async function submit(action: 'create' | 'reply' | 'resume' | 'confirm') {
  if (!props.run || busy.value) return
  const token = generation
  const runId = props.run.id
  busy.value = true
  error.value = ''
  clearTimeout(timer)
  try {
    if (action === 'create') {
      const created = await api.createAgentTask({
        run_id: runId,
        question: question.value.trim(),
        mode: mode.value,
        known_on: mode.value === 'change' ? knownOn.value : null,
      })
      if (generation !== token) return
      offset.value = 0
      selectedId.value = created.id
    } else if (current.value) {
      if (action === 'reply' && current.value.reply_token) {
        await api.replyAgent(current.value.id, {
          token: current.value.reply_token,
          reply: reply.value.trim(),
        })
      } else if (action === 'resume') await api.resumeAgent(current.value.id)
      else if (action === 'confirm' && current.value.draft) {
        const draft = current.value.draft
        await api.confirmAgent(current.value.id, {
          draft_id: draft.id,
          token: draft.token,
          project_id: draft.project_id,
          phase_id: draft.phase_id,
          base_revision_id: draft.base_revision_id,
          base_version: draft.base_version,
        })
        if (generation === token) emit('confirmed')
      }
    }
    if (generation !== token) return
    if (action === 'create') question.value = ''
    if (action === 'reply') reply.value = ''
    await load(token, runId)
  } catch (cause) {
    if (generation === token)
      error.value = cause instanceof Error ? cause.message : '请求失败，内容已保留，可重试'
  } finally {
    if (generation === token) busy.value = false
  }
}
function evidence(task: AgentTask) {
  const answer = task.answer
  if (answer)
    showEvidence(
      task.run_id,
      answer.metric,
      answer.evidence_month ?? (answer.months.length === 1 ? answer.months[0] : undefined),
      answer.evidence_month ? undefined : answer.months,
    )
}
function page(delta: number) {
  offset.value = Math.max(0, offset.value + delta)
  selectedId.value = ''
  ++generation
  refresh()
}
function refresh() {
  error.value = ''
  clearTimeout(timer)
  void load(generation, props.run?.id)
}
watch(() => state.modelConfigurationVersion, refresh)
</script>

<template>
  <section
    class="agent-chat"
    aria-label="AI 问数"
  >
    <h3>问这次预测 / 变更草稿</h3>
    <p class="note">
      问数只读；变更先生成草稿，只有你点击确认才保存新版本。模型不计算金额、不批准变更。
    </p>
    <p
      v-if="status && !status.configured"
      class="notice"
    >
      DeepSeek 未配置。配置后可用；当前测算、来源和历史功能不受影响。
    </p>
    <p v-else-if="status">
      {{ status.provider }} · {{ status.model }} · 每个任务最多 {{ status.max_calls }} 次模型调用
    </p>
    <p
      v-if="run?.status !== 'completed'"
      class="note"
    >
      先完成一次预测，再对这次结果提问。
    </p>
    <p
      v-if="run"
      class="note"
    >
      绑定 {{ run.project_names.join('、') }} · 运行 {{ run.id.slice(0, 8) }} ·
      采用该次已保存的情景与时点
    </p>
    <form @submit.prevent="submit('create')">
      <label for="agent-mode">操作方式</label>
      <select
        id="agent-mode"
        v-model="mode"
        :disabled="busy"
      >
        <option value="query">
          只读问数
        </option>
        <option
          value="change"
          :disabled="run?.kind !== 'project'"
        >
          提出变更草稿
        </option>
      </select>
      <template v-if="mode === 'change'">
        <p>
          仅支持一个分期的未售售价比例调整或交付延期。例如：一期未售售价降低5%。需绑定最新输入版本的预测。
        </p>
        <label for="agent-known">这项变更何时获知</label>
        <input
          id="agent-known"
          v-model="knownOn"
          type="date"
          :disabled="busy"
        >
      </template>
      <label for="agent-question">你的问题</label>
      <textarea
        id="agent-question"
        v-model="question"
        rows="2"
        maxlength="2000"
        placeholder="例如：未来12个月利润是多少？"
        :disabled="!enabled || busy"
      />
      <button
        type="submit"
        :disabled="!enabled || busy || !question.trim()"
      >
        {{ mode === 'query' ? '提交问数' : '生成待确认草稿' }}
      </button>
    </form>
    <p
      v-if="error"
      role="alert"
    >
      {{ error }}
    </p>
    <button
      v-if="error"
      type="button"
      @click="refresh"
    >
      重新读取状态
    </button>
    <nav aria-label="问数历史分页">
      <button
        type="button"
        :disabled="busy || offset === 0"
        @click="page(-20)"
      >
        较新任务
      </button>
      <button
        type="button"
        :disabled="busy || tasks.length < 20"
        @click="page(20)"
      >
        更早任务
      </button>
    </nav>
    <article
      v-for="task in tasks"
      :key="task.id"
    >
      <b>{{ labels[task.status] }}</b>
      <p>{{ task.question }}</p>
      <button
        v-if="task.id !== current?.id"
        type="button"
        :disabled="busy"
        @click="selectedId = task.id"
      >
        选择此任务
      </button>
      <p
        v-for="(message, index) in task.dialogue"
        :key="index"
      >
        {{ message.role === 'assistant' ? '追问' : '你的补充' }}：{{ message.content }}
      </p>
      <p
        v-if="task.error"
        role="alert"
      >
        {{ task.error }}
      </p>
      <form
        v-if="task.id === current?.id && task.status === 'awaiting_reply'"
        @submit.prevent="submit('reply')"
      >
        <label for="agent-reply">{{ task.clarification }}</label>
        <textarea
          id="agent-reply"
          v-model="reply"
          rows="2"
          maxlength="1000"
          :disabled="busy"
        />
        <button
          type="submit"
          :disabled="busy || !reply.trim()"
        >
          补充后继续
        </button>
      </form>
      <template v-if="task.answer">
        <p>{{ task.answer.period_label }} · {{ task.answer.label }}</p>
        <strong>{{
                  Number(task.answer.amount).toLocaleString('zh-CN', {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  })
                }}
          {{ task.answer.unit }}</strong>
        <p>{{ task.answer.explanation }}</p>
        <button
          type="button"
          @click="evidence(task)"
        >
          查看绑定运行来源
        </button>
        <p class="note">
          来源已按回答期间筛选；余额和缺口保留截至对应月份的累计记录。
        </p>
      </template>
      <section
        v-if="task.draft"
        aria-label="变更草稿"
      >
        <p>
          {{ task.draft.project_name }} · {{ task.draft.phase_name }} · 基础版本 v{{
            task.draft.base_version
          }}
        </p>
        <p>草稿 {{ task.draft.id.slice(0, 8) }} · 获知日期 {{ task.draft.known_on }}</p>
        <p>
          {{
            task.draft.change.field === 'price_change' ? '未售售价（元/平方米）' : '交付月份'
          }}：{{ task.draft.before }} → {{ task.draft.after }}
        </p>
        <p>这是基础参数预览，未叠加情景或工作台临时调整；不是利润测算。</p>
        <p
          v-for="warning in task.draft.preview.warnings"
          :key="warning"
        >
          {{ warning }}
        </p>
        <p v-if="task.draft.revision_id">
          已保存新输入版本。请到工作台选择不早于获知日期的信息截止及预测基准，再生成新预测；原预测未改变。
        </p>
        <button
          v-else-if="task.id === current?.id && task.status === 'awaiting_confirmation'"
          type="button"
          :disabled="busy"
          @click="submit('confirm')"
        >
          确认此草稿并保存新版本
        </button>
      </section>
      <button
        v-if="task.id === current?.id && ['failed', 'interrupted'].includes(task.status)"
        type="button"
        :disabled="busy || !status?.configured || (task.attempt ?? 1) >= 3"
        @click="submit('resume')"
      >
        继续原任务
      </button>
      <details v-if="task.steps?.length">
        <summary>处理记录 · {{ task.calls }} 次模型调用</summary>
        <p
          v-for="step in task.steps"
          :key="step.sequence"
        >
          {{ step.message }}
        </p>
      </details>
    </article>
    <p
      v-if="tasks.length"
      class="note"
    >
      任务已保存，关闭页面后可在同一预测继续查看。
    </p>
  </section>
</template>

<style scoped>
.agent-chat {
  padding: 13px;
  background: var(--soft);
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.7;
  overflow-wrap: anywhere;
}
h3 {
  margin: 0;
  font-size: 14px;
}
p {
  margin: 7px 0;
}
.note {
  color: var(--muted);
}
.notice {
  color: var(--accent);
}
label {
  display: block;
  margin-bottom: 5px;
}
textarea {
  width: 100%;
  box-sizing: border-box;
  resize: vertical;
  font: inherit;
  color: inherit;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 7px;
}
select,
input {
  max-width: 100%;
  color: inherit;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 6px;
  font: inherit;
}
button {
  color: var(--accent);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 6px 10px;
  font: inherit;
  margin-top: 6px;
  cursor: pointer;
}
button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
article {
  border-top: 1px solid var(--border);
  padding-top: 10px;
  margin-top: 12px;
}
strong {
  font-size: 17px;
  color: var(--accent);
}
summary {
  cursor: pointer;
}
</style>
