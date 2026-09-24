<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { api } from '../../api/client'
import type { AgentStatus, AgentTask, Run } from '../../api/types'
import { showEvidence } from '../../state'

const props = defineProps<{ run: Run | null }>()
const status = ref<AgentStatus | null>(null)
const tasks = ref<AgentTask[]>([])
const question = ref('')
const reply = ref('')
const error = ref('')
const busy = ref(false)
let generation = 0
let timer: ReturnType<typeof setTimeout> | undefined
const current = computed(() => tasks.value[0])
const enabled = computed(() => status.value?.configured && props.run?.status === 'completed')
const labels: Record<AgentTask['status'], string> = {
  queued: '已保存，等待处理',
  running: '正在理解问题',
  awaiting_reply: '需要你补充',
  completed: '回答已保存',
  failed: '处理失败',
  interrupted: '服务中断，可继续',
}
async function load(token: number, runId?: string) {
  try {
    const [configuration, saved] = await Promise.all([
      api.agentStatus(),
      runId ? api.agentTasks(runId) : Promise.resolve([]),
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
async function submit(action: 'create' | 'reply' | 'resume') {
  if (!props.run || busy.value) return
  const token = generation
  const runId = props.run.id
  busy.value = true
  error.value = ''
  clearTimeout(timer)
  try {
    if (action === 'create')
      await api.createAgentTask({ run_id: runId, question: question.value.trim() })
    else if (current.value) {
      if (action === 'reply' && current.value.reply_token) {
        await api.replyAgent(current.value.id, {
          token: current.value.reply_token,
          reply: reply.value.trim(),
        })
      } else if (action === 'resume') await api.resumeAgent(current.value.id)
    }
    if (generation !== token) return
    question.value = ''
    reply.value = ''
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
    )
}
function refresh() {
  error.value = ''
  clearTimeout(timer)
  void load(generation, props.run?.id)
}
</script>

<template>
  <section
    class="agent-chat"
    aria-label="AI 问数"
  >
    <h3>问这次预测</h3>
    <p class="note">
      只读问数：模型理解问题，程序读取金额。不会修改计划，也不会替你确认任何变更。
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
      绑定运行 {{ run.id.slice(0, 8) }} · 采用该次已保存的情景与时点
    </p>
    <form @submit.prevent="submit('create')">
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
        :disabled="
          !enabled ||
            busy ||
            !question.trim() ||
            (current && ['queued', 'running', 'awaiting_reply'].includes(current.status))
        "
      >
        提交问数
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
    <article
      v-for="task in tasks"
      :key="task.id"
    >
      <b>{{ labels[task.status] }}</b>
      <p>{{ task.question }}</p>
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
          跨月回答的来源入口展示该指标全周期记录，可按回答月份核对。
        </p>
      </template>
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
