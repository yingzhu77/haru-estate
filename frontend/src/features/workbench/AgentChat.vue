<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { api } from '../../api/client'
import type { AgentStatus, AgentTask, Run } from '../../api/types'
import { showEvidence, state } from '../../state'
import { isLocalEntry } from '../../deployment'

const localEntry = isLocalEntry(window.location.hostname)

const props = defineProps<{ run: Run | null }>()
const emit = defineEmits<{ confirmed: [] }>()
const status = ref<AgentStatus | null>(null)
const tasks = ref<AgentTask[]>([])
const savedVersions = ref<Record<string, number>>({})
const pendingVersions = new Map<string, number>()
const questionInput = ref<HTMLTextAreaElement | null>(null)
const selectedId = ref('')
const offset = ref(0)
const question = ref('')
const mode = ref<'query' | 'change'>('query')
const knownOn = ref(new Date().toLocaleDateString('en-CA'))
const reply = ref('')
const error = ref('')
const busy = ref(false)
let generation = 0
let readSequence = 0
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
  awaiting_confirmation: '方案待你确认',
  completed: '回答已保存',
  failed: '处理失败',
  interrupted: '服务中断，可继续',
}
async function load(token: number, runId?: string) {
  const read = ++readSequence
  try {
    const [configuration, saved] = await Promise.all([
      api.agentStatus(),
      runId ? api.agentTasks(runId, offset.value) : Promise.resolve([]),
    ])
    if (generation !== token || read !== readSequence) return
    status.value = configuration
    tasks.value = saved
    for (const task of saved) {
      const draft = task.draft
      if (draft?.revision_id && savedVersions.value[draft.revision_id] === undefined
        && pendingVersions.get(draft.revision_id) !== token)
        void loadSavedVersion(token, draft.project_id, draft.revision_id)
    }
    if (!selectedId.value && saved[0]) selectedId.value = saved[0].id
    if (saved.some((task) => ['queued', 'running'].includes(task.status))) {
      timer = setTimeout(() => void load(token, runId), 1200)
    }
  } catch (cause) {
    if (generation === token && read === readSequence)
      error.value = cause instanceof Error ? cause.message : '助手记录读取失败'
  }
}
async function loadSavedVersion(token: number, projectId: string, revisionId: string) {
  pendingVersions.set(revisionId, token)
  try {
    const revision = await api.input(projectId, revisionId)
    if (generation === token) savedVersions.value[revisionId] = revision.version
  } catch {
    // The saved revision ID remains visible. Optional metadata must not stop task polling.
  } finally {
    if (pendingVersions.get(revisionId) === token) pendingVersions.delete(revisionId)
  }
}
function refillQuestion(task: AgentTask) {
  if (busy.value || question.value.trim()) return
  question.value = task.question
  mode.value = task.mode
  if (task.known_on) knownOn.value = task.known_on
  void nextTick(() => questionInput.value?.focus())
}
watch(
  () => props.run?.id,
  () => {
    ++generation
    clearTimeout(timer)
    tasks.value = []
    savedVersions.value = {}
    pendingVersions.clear()
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
  ++readSequence
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
    aria-label="预测助手"
  >
    <h3>预测助手</h3>
    <p class="note">
      查询已保存的预测，或提出计划调整。金额由程序计算，是否采用调整由你决定。
    </p>
    <p
      v-if="status && !status.configured"
      class="notice"
    >
      DeepSeek 未配置。{{ localEntry ? '请打开右上角“AI 设置”连接助手' : '请联系演示管理员开启助手' }}；仍可正常测算、查看历史和数据来源。
    </p>
    <p v-else-if="status">
      已连接 {{ status.provider }} · {{ status.model }}
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
      当前预测：{{ run.project_names.join('、') }} · 编号 {{ run.id.slice(0, 8) }} ·
      查询范围以这份预测保存的项目、情景和期间为准
    </p>
    <p
      v-if="run"
      class="note"
    >
      对话随这份预测保存。切换或生成新预测后，旧对话仍在原预测中。
      <RouterLink :to="`/runs/${run.id}`">
        打开本次预测与对话
      </RouterLink>
      · <RouterLink to="/runs">
        查找其他预测的对话
      </RouterLink>
    </p>
    <form @submit.prevent="submit('create')">
      <label for="agent-mode">你想做什么？</label>
      <select
        id="agent-mode"
        v-model="mode"
        :disabled="busy"
      >
        <option value="query">
          查看预测结果
        </option>
        <option
          value="change"
          :disabled="run?.kind !== 'project'"
        >
          提出调整方案
        </option>
      </select>
      <p
        v-if="mode === 'query'"
        class="note"
      >
        查询本次预测的利润、现金和数据来源，不修改项目数据。
      </p>
      <p
        v-else
        class="note"
      >
        先生成方案供你核对；确认采用后才保存新版本，再重新测算查看影响。原预测会保留。
      </p>
      <p
        v-if="run?.kind === 'portfolio'"
        class="note"
      >
        汇总预测支持查询结果；如需调整计划，请先切换到对应的单项目预测。
      </p>
      <template v-if="mode === 'change'">
        <p>
          说明想调整的分期和幅度，例如“1期住宅未售售价降低5%”或“2期住宅交付推迟3个月”。目前每次支持一项调整；请使用按最新数据生成的单项目预测。
        </p>
        <label for="agent-known">你从哪天知道这项调整？</label>
        <input
          id="agent-known"
          v-model="knownOn"
          type="date"
          :disabled="busy"
        >
      </template>
      <label for="agent-question">{{ mode === 'query' ? '你想了解什么？' : '你想怎样调整计划？' }}</label>
      <textarea
        id="agent-question"
        ref="questionInput"
        v-model="question"
        rows="2"
        maxlength="2000"
        :placeholder="mode === 'query' ? '例如：未来12个月利润是多少？' : '例如：2期住宅交付推迟3个月'"
        :disabled="!enabled || busy"
      />
      <button
        type="submit"
        :disabled="!enabled || busy || !question.trim()"
      >
        {{ mode === 'query' ? '查询结果' : '生成调整方案' }}
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
    <nav aria-label="助手记录翻页">
      <button
        type="button"
        :disabled="busy || offset === 0"
        @click="page(-20)"
      >
        较新记录
      </button>
      <button
        type="button"
        :disabled="busy || tasks.length < 20"
        @click="page(20)"
      >
        更早记录
      </button>
    </nav>
    <article
      v-for="task in tasks"
      :key="task.id"
    >
      <b>{{ task.draft?.revision_id ? '方案已采用' : labels[task.status] }}</b>
      <p>{{ task.question }}</p>
      <button
        v-if="task.id !== current?.id"
        type="button"
        :disabled="busy"
        @click="selectedId = task.id"
      >
        继续这条记录
      </button>
      <p
        v-for="(message, index) in task.dialogue"
        :key="index"
      >
        {{ message.role === 'assistant' ? '助手想确认' : '你的补充' }}：{{ message.content }}
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
          提交补充说明
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
          查看这笔金额的来源
        </button>
        <p class="note">
          来源已按回答期间筛选；余额和缺口保留截至对应月份的累计记录。
        </p>
      </template>
      <section
        v-if="task.draft"
        aria-label="待核对的调整方案"
      >
        <p>
          {{ task.draft.project_name }} · {{ task.draft.phase_name }} · 调整前数据版本 v{{
            task.draft.base_version
          }}
        </p>
        <p>方案编号 {{ task.draft.id.slice(0, 8) }} · 信息获知日期 {{ task.draft.known_on }}</p>
        <p>
          {{
            task.draft.change.field === 'price_change' ? '未售售价（元/平方米）' : '交付月份'
          }}：{{ task.draft.before }} → {{ task.draft.after }}
        </p>
        <p>这里展示调整前后的参数，尚未计算利润和现金的变化，也未叠加工作台的情景调整。</p>
        <p
          v-for="warning in task.draft.preview.warnings"
          :key="warning"
        >
          {{ warning }}
        </p>
        <template v-if="task.draft.revision_id">
          <p>
            <strong v-if="savedVersions[task.draft.revision_id] !== undefined">已保存为数据版本 v{{ savedVersions[task.draft.revision_id] }}</strong>
            <strong v-else>新数据版本已保存</strong>
            （版本编号 {{ task.draft.revision_id.slice(0, 8) }}）。上方 v{{ task.draft.base_version }} 是调整前版本。
          </p>
          <p>保存数据不会自动生成新预测，原预测保持不变。</p>
          <p>
            <RouterLink to="/">
              前往预测工作台
            </RouterLink>，选择“{{ task.draft.project_name }}”，将信息截止日和预测基准日设为不早于 {{ task.draft.known_on }}，再生成预测查看调整效果。
          </p>
        </template>
        <button
          v-else-if="task.id === current?.id && task.status === 'awaiting_confirmation'"
          type="button"
          :disabled="busy"
          @click="submit('confirm')"
        >
          确认采用，保存新版本
        </button>
      </section>
      <button
        v-if="task.id === current?.id && ['failed', 'interrupted'].includes(task.status)"
        type="button"
        :disabled="busy || !status?.configured || (task.attempt ?? 1) >= 3"
        @click="submit('resume')"
      >
        重试这条记录
      </button>
      <template v-if="['failed', 'interrupted'].includes(task.status)">
        <p class="note">
          已用 {{ task.calls }}/{{ status?.max_calls ?? 3 }} 次模型调用，失败也计入次数。系统不会自动重试。
          <span v-if="(task.attempt ?? 1) >= 3">这条记录已达到处理次数上限，不能再重试。</span>
          <span v-else-if="task.calls >= (status?.max_calls ?? 3)">模型调用次数已用完，恢复仅能继续已保存的步骤，不能再次请求模型。</span>
          <span v-else>重试可能再次调用模型并产生费用。</span>
        </p>
        <button
          type="button"
          :disabled="busy || !!question.trim()"
          @click="refillQuestion(task)"
        >
          填回原问题
        </button>
        <p class="note">
          输入框已有内容时请先清空。填回不会发送请求；请补齐需要的说明，核对当前项目和日期，再手动提交。旧记录保留。
        </p>
      </template>
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
      记录已保存，关闭页面后可在同一预测继续查看。
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
