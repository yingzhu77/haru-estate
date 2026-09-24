<script setup lang="ts">
import {
  CircleCheckFilled,
  WarningFilled,
  Clock,
  Connection,
  ArrowRight,
  DocumentChecked,
} from '@element-plus/icons-vue'
import type { Run } from '../../api/types'
import { showEvidence, state } from '../../state'
import { statusLabels } from './useWorkbench'
import AgentChat from './AgentChat.vue'
defineProps<{ run: Run | null; busy: boolean; pollError: string }>()
const emit = defineEmits<{ resume: []; refresh: [] }>()
const timeLabel = (value: string) => {
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}
</script>

<template>
  <aside
    class="panel activity-panel"
    aria-label="运行记录与协作"
  >
    <div class="activity-heading">
      <img
        v-if="state.theme === 'acg'"
        src="/brand/logo.png"
        alt="晴屿助手头像"
        width="37"
        height="37"
      >
      <div
        v-else
        class="assistant-symbol"
      >
        <el-icon><Connection /></el-icon>
      </div>
      <h2>Agent 协作</h2>
      <span class="ai-state">程序测算 · AI 问数</span>
    </div>
    <div
      class="flow-strip"
      aria-label="数据检查、程序计算、来源核对"
    >
      <div>
        <el-icon :class="{ done: run?.status === 'completed' }">
          <DocumentChecked />
        </el-icon><span>数据检查</span>
      </div>
      <span class="flow-line" />
      <div>
        <el-icon :class="{ done: run?.status === 'completed' }">
          <Connection />
        </el-icon><span>程序测算</span>
      </div>
      <span class="flow-line" />
      <div>
        <el-icon><CircleCheckFilled /></el-icon><span>来源核对</span>
      </div>
    </div>
    <div
      v-if="pollError"
      class="activity-card warning-card"
      role="alert"
    >
      <b>状态暂未更新</b>
      <p>{{ pollError }}</p>
      <el-button
        size="small"
        @click="emit('refresh')"
      >
        重新获取状态
      </el-button>
    </div>
    <div
      v-if="run"
      class="activity-card run-card"
    >
      <div class="card-heading">
        <el-icon>
          <CircleCheckFilled v-if="run.status === 'completed'" /><WarningFilled
            v-else-if="['failed', 'incomplete', 'interrupted'].includes(run.status)"
          /><Clock v-else />
        </el-icon><b>{{ statusLabels[run.status] ?? run.status }}</b><time>{{ timeLabel(run.created_at) }}</time>
      </div>
      <p v-if="run.status === 'completed'">
        本次测算已保存。指标、明细与来源绑定同一份输入快照。
      </p>
      <p v-else-if="run.status === 'interrupted'">
        服务中断前的输入已保存。继续运行将使用原快照。
      </p>
      <p
        v-else-if="run.error"
        class="run-error"
      >
        {{ run.error }}
      </p>
      <p v-else>
        任务已保存，关闭此页面不会取消测算。
      </p>
      <span class="run-id">运行 {{ run.id.slice(0, 12) }} · 第 {{ run.attempt }} 次尝试</span>
      <el-button
        v-if="run.status === 'interrupted'"
        type="primary"
        size="small"
        :loading="busy"
        @click="emit('resume')"
      >
        继续原运行
      </el-button>
      <button
        v-if="run.result && run.status === 'completed'"
        class="text-action"
        @click="showEvidence(run.id)"
      >
        查看计算依据 <el-icon><ArrowRight /></el-icon>
      </button>
      <RouterLink
        :to="`/runs/${run.id}`"
        class="text-action"
      >
        完整运行记录 <el-icon><ArrowRight /></el-icon>
      </RouterLink>
    </div>
    <div
      v-else
      class="activity-card ready-card"
    >
      <div class="card-heading">
        <el-icon><Clock /></el-icon><b>等待首次预测</b>
      </div>
      <p>选择项目与预测时点，检查左侧参数后生成预测。计算过程和来源将在这里保留。</p>
    </div>
    <div
      v-if="run?.steps?.length"
      class="step-list"
      aria-label="真实执行步骤"
    >
      <div
        v-for="step in run.steps"
        :key="`${step.attempt}-${step.sequence}`"
        class="step-item"
      >
        <span
          class="step-dot"
          :class="{ 'step-failed': step.status === 'failed' }"
        />
        <div>
          <div class="step-heading">
            <b>{{ step.name }}</b><time>{{ timeLabel(step.created_at) }}</time>
          </div>
          <p>{{ step.message }}</p>
          <span class="step-meta">{{ statusLabels[step.status] ?? step.status }} · 尝试 {{ step.attempt }}</span>
        </div>
      </div>
    </div>
    <div
      v-if="run?.result?.warnings.length"
      class="activity-card warning-card"
    >
      <div class="card-heading">
        <el-icon><WarningFilled /></el-icon><b>需关注事项</b>
      </div>
      <ul>
        <li
          v-for="warning in run.result.warnings"
          :key="warning"
        >
          {{ warning }}
        </li>
      </ul>
    </div>
    <AgentChat :run="run" />
    <div class="activity-card explainer">
      <b>每一个数字，都有来处</b>
      <p>销售、回款与收入确认分开计算；开发投入、成本结转和实际付款分别追踪。</p>
      <p>程序提供测算和运行记录；AI 问数需要配置 DeepSeek，回答绑定已保存的预测。</p>
    </div>
    <div class="activity-footer">
      <span class="live-indicator" />程序计算 · 来源可查<RouterLink to="/runs">
        历史版本
      </RouterLink>
    </div>
  </aside>
</template>

<style scoped>
.activity-panel {
  padding: 18px 15px;
  display: flex;
  flex-direction: column;
  gap: 17px;
}
.activity-heading {
  display: flex;
  align-items: center;
  gap: 9px;
}
.activity-heading h2 {
  font-size: 17px;
  margin: 0;
  white-space: nowrap;
}
.activity-heading img {
  border-radius: 50%;
  object-fit: contain;
}
.assistant-symbol {
  height: 37px;
  width: 37px;
  border-radius: 50%;
  border: 1px solid var(--border);
  background: var(--soft);
  display: grid;
  place-items: center;
  font-size: 22px;
  color: var(--accent);
}
.ai-state {
  margin-left: auto;
  background: #fff7e9;
  color: #99621c;
  border: 1px solid #f1dfbd;
  padding: 5px 6px;
  border-radius: 15px;
  font-size: 9px;
  white-space: nowrap;
}
.flow-strip {
  display: flex;
  align-items: flex-start;
  margin: 5px 6px 0;
}
.flow-strip div {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}
.flow-strip .el-icon {
  border-radius: 50%;
  background: var(--soft);
  padding: 5px;
  width: 29px;
  height: 29px;
  color: var(--muted);
  font-size: 20px;
}
.flow-strip .el-icon.done {
  color: #fff;
  background: var(--accent);
}
.flow-strip div span {
  font-size: 10px;
  white-space: nowrap;
}
.flow-line {
  height: 1px;
  background: var(--border);
  flex: 1;
  margin: 14px 6px 0;
}
.activity-card {
  padding: 15px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--soft);
  font-size: 12px;
}
.card-heading {
  display: flex;
  align-items: center;
  gap: 7px;
}
.card-heading .el-icon {
  font-size: 21px;
  color: var(--accent);
}
.card-heading b {
  font-size: 14px;
}
time {
  margin-left: auto;
  color: var(--muted);
  font-size: 10px;
}
.activity-card p {
  line-height: 1.8;
  margin: 10px 0;
  overflow-wrap: anywhere;
}
.run-id {
  color: var(--muted);
  display: block;
  font-size: 10px;
  margin-bottom: 9px;
}
.text-action {
  border: 0;
  padding: 3px 0;
  display: flex;
  align-items: center;
  gap: 4px;
  background: none;
  color: var(--accent);
  font-size: 11px;
  line-height: 1.7;
}
.run-error {
  color: #ae453c;
}
.warning-card {
  background: #fffbf3;
  border-color: #ecdfc5;
  color: #895d21;
}
.warning-card .el-icon {
  color: #b57c27;
}
.warning-card ul {
  margin: 10px 0 0;
  padding-left: 16px;
  line-height: 1.8;
}
.explainer {
  background: transparent;
  border-style: dashed;
  margin-top: auto;
}
.explainer p {
  color: var(--muted);
  font-size: 11px;
}
.step-list {
  padding: 1px 4px 0;
  max-height: 235px;
  overflow-y: auto;
}
.step-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 0 0 16px;
  position: relative;
}
.step-item:not(:last-child)::before {
  content: '';
  position: absolute;
  left: 4px;
  top: 12px;
  bottom: 0;
  width: 1px;
  background: var(--border);
}
.step-item > div {
  flex: 1;
  min-width: 0;
}
.step-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--accent);
  margin-top: 5px;
  flex-shrink: 0;
}
.step-dot.step-failed {
  background: #b54a3e;
}
.step-heading {
  display: flex;
  align-items: center;
  font-size: 11px;
  gap: 8px;
}
.step-item p {
  margin: 5px 0;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.6;
}
.step-meta {
  color: var(--muted);
  font-size: 9px;
}
.activity-footer {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 10px;
  color: var(--muted);
  border-top: 1px solid var(--border);
  padding-top: 14px;
}
.activity-footer a {
  margin-left: auto;
}
.live-indicator {
  height: 6px;
  width: 6px;
  border-radius: 50%;
  background: #398471;
}
</style>
