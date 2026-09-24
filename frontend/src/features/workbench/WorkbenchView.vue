<script setup lang="ts">
import { computed, ref } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import {
  ArrowRight,
  Histogram,
  TrendCharts,
  PieChart,
  Coin,
  Calendar,
  DataLine,
  Document,
  Plus,
  Refresh,
} from '@element-plus/icons-vue'
import type { MonthResult } from '../../api/types'
import { state, formatMoney, showEvidence } from '../../state'
import { scenarioLabels, statusLabels, useWorkbench } from './useWorkbench'
import ForecastChart from './ForecastChart.vue'
import ParameterPanel from './ParameterPanel.vue'
import RunActivity from './RunActivity.vue'

const {
  editor,
  currentRevision,
  currentRun,
  resultRun,
  result,
  selectedIds,
  loading,
  busy,
  error,
  pollError,
  validation,
  dirtySinceResult,
  generate,
  resume,
  loadScope,
  refreshInputs,
  markDirty,
  refreshStatus,
} = useWorkbench()
const chartView = ref<'profit' | 'cash' | 'lifecycle'>('profit')
const sensitivityOpen = ref(false)
const detailExpanded = ref(false)
const summary = computed(() => result.value?.summary)
const rows = computed(
  () =>
    result.value?.months.filter(
      (row) => chartView.value === 'lifecycle' || result.value!.target_months.includes(row.month),
    ) ?? [],
)
const predictionPeriod = computed(() => {
  const months = result.value?.target_months ?? []
  return months.length ? `${months[0]} — ${months.at(-1)}` : '下一个自然月起，逐月预测12个月'
})
const displayedTitle = computed(() =>
  resultRun.value ? resultRun.value.project_names.join(' / ') : '利润与现金流概览',
)
const oldResult = computed(() => !!resultRun.value && currentRun.value?.id !== resultRun.value.id)
const changedTime = computed(
  () =>
    !!resultRun.value &&
    (resultRun.value.forecast_origin !== state.forecastOrigin ||
      resultRun.value.information_cutoff !== state.informationCutoff),
)
const periodLabels: Record<string, string> = {
  actual: '实际',
  estimate: '估计',
  forecast: '预测',
  mixed: '混合',
}

function inspect(metric = 'profit', month?: string) {
  if (resultRun.value) showEvidence(resultRun.value.id, metric, month)
}
function inspectChart(month: string, metric: string) {
  inspect(metric, month)
}
function onCellClick(row: MonthResult, column: { property: string }) {
  if (
    [
      'revenue',
      'cogs',
      'profit',
      'cumulative_profit',
      'collections',
      'net_cash_flow',
      'payments',
      'expenses',
      'taxes',
      'interest',
    ].includes(column.property)
  ) {
    inspect(column.property, row.month)
  }
}
function formatCell(row: MonthResult, column: { property: string }) {
  return formatMoney(row[column.property as keyof MonthResult])
}
onBeforeRouteLeave(async () => {
  if (!dirtySinceResult.value) return true
  try {
    await ElMessageBox.confirm(
      '情景草稿还没有生成预测，本次打开页面期间会保留；刷新或关闭后未提交内容将丢失。',
      '保留草稿并离开？',
      {
        confirmButtonText: '保留并离开',
        cancelButtonText: '继续编辑',
        type: 'warning',
      },
    )
    return true
  } catch {
    return false
  }
})
</script>

<template>
  <div class="workbench">
    <div class="workbench-toolbar">
      <div
        class="mode-control"
        role="group"
        aria-label="预测范围"
      >
        <button
          :class="{ active: state.mode === 'project' }"
          :aria-pressed="state.mode === 'project'"
          @click="state.mode = 'project'"
        >
          单项目预测
        </button>
        <button
          :class="{ active: state.mode === 'portfolio' }"
          :aria-pressed="state.mode === 'portfolio'"
          @click="state.mode = 'portfolio'"
        >
          项目汇总 <span>{{ state.selectedProjectIds.length }}</span>
        </button>
      </div>
      <span class="period-note"><el-icon><Calendar /></el-icon>{{ predictionPeriod }}</span>
      <RouterLink
        to="/projects"
        class="quiet-link add-project"
      >
        <el-icon><Plus /></el-icon>新增项目
      </RouterLink>
      <RouterLink
        to="/runs"
        class="quiet-link"
      >
        预测记录 <el-icon><ArrowRight /></el-icon>
      </RouterLink>
    </div>
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      show-icon
      :closable="false"
      class="workbench-alert"
    >
      <template #default>
        <el-button
          size="small"
          :icon="Refresh"
          @click="loadScope"
        >
          重新加载输入与记录
        </el-button>
        <p>如请求已提交，请先查看历史运行，再决定是否重试。已有结果不会被删除。</p>
      </template>
    </el-alert>
    <div
      v-if="validation && !loading"
      class="validation-note"
      role="status"
    >
      {{ validation }}
    </div>
    <div class="workbench-grid">
      <ParameterPanel
        :revision="currentRevision"
        :scenario="editor.scenario"
        :loading="loading"
        :busy="busy"
        :disabled="!!validation"
        :selected-count="selectedIds.length"
        @update:scenario="editor.scenario = $event"
        @changed="markDirty"
        @generate="generate"
      />
      <div class="results-column">
        <section
          class="panel overview-panel"
          aria-label="利润与现金流概览"
        >
          <div class="section-header">
            <div>
              <h2>利润与现金流概览</h2>
              <span class="section-caption">模拟管理口径 · 单位：万元</span>
            </div>
            <button
              class="text-link"
              :disabled="!result"
              @click="inspect()"
            >
              来源追溯 <el-icon><ArrowRight /></el-icon>
            </button>
          </div>
          <div
            v-if="resultRun"
            class="result-version"
          >
            <span>{{ displayedTitle }} · {{ scenarioLabels[resultRun.scenario] }}情景</span>
            <RouterLink :to="`/runs/${resultRun.id}`">
              运行 {{ resultRun.id.slice(0, 8) }}
            </RouterLink>
          </div>
          <div
            v-if="oldResult || dirtySinceResult || changedTime"
            class="version-warning"
            role="status"
          >
            {{
              oldResult
                ? '当前任务尚未产生完整新结果，下面保留上一次已完成预测。'
                : '输入条件已变化，下面仍为已保存版本；提交预测后更新。'
            }}
          </div>
          <div class="metrics-grid">
            <button
              class="metric-card"
              :disabled="!result"
              @click="inspect('profit', result?.target_months[0])"
            >
              <span class="metric-label"><el-icon><Histogram /></el-icon>下月利润</span><strong
                class="money"
                :class="{ negative: Number(summary?.next_month_profit) < 0 }"
              >{{ formatMoney(summary?.next_month_profit) }}</strong><span class="metric-foot">{{ result?.target_months[0] ?? '等待生成预测' }}</span>
            </button>
            <button
              class="metric-card"
              :disabled="!result"
              @click="inspect('twelve_month_profit')"
            >
              <span class="metric-label"><el-icon><TrendCharts /></el-icon>未来12个月利润</span><strong
                class="money"
                :class="{ negative: Number(summary?.twelve_month_profit) < 0 }"
              >{{ formatMoney(summary?.twelve_month_profit) }}</strong><span class="metric-foot">{{
                result ? '目标期间累计预测' : '历史数据 + 未来业务计划'
              }}</span>
            </button>
            <button
              class="metric-card range-card"
              :disabled="!result"
              @click="sensitivityOpen = true"
            >
              <span class="metric-label"><el-icon><PieChart /></el-icon>利润情景区间</span><strong class="money range-value">{{
                summary
                  ? `${formatMoney(summary.range_low)} ~ ${formatMoney(summary.range_high)}`
                  : '—'
              }}</strong><span class="metric-foot">三种情景范围 · 非置信区间</span>
            </button>
            <button
              class="metric-card gap-card"
              :disabled="!result"
              @click="inspect('uncovered_gap')"
            >
              <span class="metric-label"><el-icon><Coin /></el-icon>最大资金缺口</span><strong class="money">{{ formatMoney(summary?.max_funding_gap) }}</strong><span class="metric-foot">{{
                state.mode === 'portfolio' ? '逐月汇总各项目未覆盖缺口' : '全周期未覆盖缺口峰值'
              }}</span>
            </button>
          </div>
          <div
            v-if="resultRun"
            class="snapshot-caption"
          >
            预测基准 {{ resultRun.forecast_origin }} · 信息截止 {{ resultRun.information_cutoff }} ·
            {{ result?.rule_version
            }}<span>快照 {{ resultRun.revision_ids.map((id) => id.slice(0, 6)).join(' / ') }}</span>
          </div>
        </section>

        <section class="panel trend-panel">
          <div class="section-header">
            <h2>
              {{ chartView === 'lifecycle' ? '全周期月度趋势' : '未来12个月趋势' }}
            </h2>
            <div
              class="chart-switch"
              role="group"
              aria-label="趋势类型"
            >
              <button
                :class="{ active: chartView === 'profit' }"
                :aria-pressed="chartView === 'profit'"
                @click="chartView = 'profit'"
              >
                利润
              </button><button
                :class="{ active: chartView === 'cash' }"
                :aria-pressed="chartView === 'cash'"
                @click="chartView = 'cash'"
              >
                现金流
              </button><button
                :class="{ active: chartView === 'lifecycle' }"
                :aria-pressed="chartView === 'lifecycle'"
                @click="chartView = 'lifecycle'"
              >
                全周期
              </button>
            </div>
          </div>
          <ForecastChart
            v-if="result"
            :result="result"
            :view="chartView"
            @inspect="inspectChart"
          />
          <div
            v-else
            class="forecast-empty"
          >
            <div class="empty-chart-icon">
              <el-icon><DataLine /></el-icon>
            </div>
            <h3>
              {{ busy ? '正在根据已保存输入测算' : '让项目计划，变成可追溯的预测' }}
            </h3>
            <p>选择预测时点与情景，生成下月、未来12个月及全周期结果。</p>
            <span>历史实际 → 合同与计划 → 程序测算 → 来源核对</span><el-button
              v-if="!busy"
              type="primary"
              plain
              :disabled="!!validation || loading"
              @click="generate"
            >
              生成第一份预测
            </el-button>
          </div>
          <div class="driver-strip">
            <span class="driver-title">关键驱动</span>
            <div>
              <el-icon><Calendar /></el-icon><span><b>交付节奏</b><small>收入与成本确认</small></span>
            </div>
            <div>
              <el-icon><TrendCharts /></el-icon><span><b>未售价格</b><small>未来销售规模</small></span>
            </div>
            <div>
              <el-icon><Coin /></el-icon><span><b>付款安排</b><small>资金缺口与利息</small></span>
            </div>
            <button
              class="sensitivity-button"
              :disabled="!result"
              @click="sensitivityOpen = true"
            >
              敏感性分析 <el-icon><ArrowRight /></el-icon>
            </button>
          </div>
        </section>

        <section
          v-if="state.mode === 'portfolio' && currentRun?.members?.length"
          class="panel contribution-panel"
        >
          <div class="section-header">
            <h2>项目贡献与完成情况</h2>
            <span class="section-caption">固定本次成员 · 不跨项目调拨资金</span>
          </div>
          <p
            v-if="currentRun.status !== 'completed'"
            class="incomplete-note"
          >
            汇总尚未完整完成，以下展示各子项目状态；未完成项目不按零计入。
          </p>
          <el-table
            :data="currentRun.members"
            size="small"
            class="contribution-table"
          >
            <el-table-column
              prop="project_name"
              label="项目"
              min-width="130"
            /><el-table-column
              prop="status"
              label="状态"
              min-width="110"
            >
              <template #default="{ row }">
                <span
                  :class="{
                    negative: ['failed', 'incomplete'].includes(row.status),
                  }"
                >{{ statusLabels[row.status] ?? row.status }}</span>
              </template>
            </el-table-column><el-table-column
              label="12个月利润 / 万元"
              align="right"
              min-width="145"
            >
              <template #default="{ row }">
                {{ formatMoney(row.profit) }}
              </template>
            </el-table-column><el-table-column
              label="绑定预测"
              width="90"
              align="right"
            >
              <template #default="{ row }">
                <RouterLink :to="`/runs/${row.run_id}`">
                  查看
                  <el-icon>
                    <ArrowRight />
                  </el-icon>
                </RouterLink>
              </template>
            </el-table-column>
          </el-table>
          <p class="table-note">
            项目贡献绑定本次子运行，之后新增项目或修订数据不会改变本次汇总。
          </p>
        </section>

        <section class="panel monthly-panel">
          <div class="section-header">
            <h2>月度预测明细</h2>
            <button
              class="text-link"
              :disabled="!result"
              @click="detailExpanded = !detailExpanded"
            >
              {{ detailExpanded ? '收起明细' : '展开明细' }}
              <el-icon><ArrowRight /></el-icon>
            </button>
          </div>
          <el-table
            v-if="result"
            :data="rows"
            :max-height="detailExpanded ? 620 : 260"
            size="small"
            class="monthly-table"
            @cell-click="onCellClick"
          >
            <el-table-column
              prop="month"
              label="月份"
              width="93"
              fixed
            />
            <el-table-column
              prop="period"
              label="性质"
              width="62"
            >
              <template #default="{ row }">
                <span
                  class="period-chip"
                  :class="{ actual: row.period === 'actual' }"
                >{{ periodLabels[row.period] }}</span>
              </template>
            </el-table-column>
            <template v-if="chartView === 'cash'">
              <el-table-column
                prop="collections"
                label="销售回款"
                align="right"
                min-width="100"
                :formatter="formatCell"
              />
              <el-table-column
                prop="payments"
                label="开发付款"
                align="right"
                min-width="100"
                :formatter="formatCell"
              />
              <el-table-column
                prop="borrowing"
                label="融资借入"
                align="right"
                min-width="100"
                :formatter="formatCell"
              />
              <el-table-column
                prop="repayment"
                label="归还本金"
                align="right"
                min-width="100"
                :formatter="formatCell"
              />
              <el-table-column
                prop="net_cash_flow"
                label="净现金流"
                align="right"
                min-width="100"
                :formatter="formatCell"
              />
              <el-table-column
                prop="uncovered_gap"
                label="未覆盖缺口"
                align="right"
                min-width="105"
                :formatter="formatCell"
              />
            </template>
            <template v-else>
              <el-table-column
                prop="revenue"
                label="确认收入"
                align="right"
                min-width="100"
                :formatter="formatCell"
              />
              <el-table-column
                prop="cogs"
                label="结转成本"
                align="right"
                min-width="100"
                :formatter="formatCell"
              />
              <el-table-column
                prop="expenses"
                label="费用"
                align="right"
                min-width="86"
                :formatter="formatCell"
              />
              <el-table-column
                prop="taxes"
                label="税费"
                align="right"
                min-width="86"
                :formatter="formatCell"
              />
              <el-table-column
                prop="interest"
                label="利息"
                align="right"
                min-width="86"
                :formatter="formatCell"
              />
              <el-table-column
                prop="profit"
                label="利润"
                align="right"
                min-width="100"
              >
                <template #default="{ row }">
                  <button
                    class="table-value money"
                    :class="{ negative: Number(row.profit) < 0 }"
                    @click.stop="inspect('profit', row.month)"
                  >
                    {{ formatMoney(row.profit) }}
                  </button>
                </template>
              </el-table-column>
              <el-table-column
                prop="cumulative_profit"
                label="预测起累计利润"
                align="right"
                min-width="135"
                :formatter="formatCell"
              />
            </template>
            <el-table-column
              label="依据"
              width="64"
              fixed="right"
            >
              <template #default="{ row }">
                <button
                  class="text-link"
                  @click.stop="
                    inspect(chartView === 'cash' ? 'net_cash_flow' : 'profit', row.month)
                  "
                >
                  查看
                </button>
              </template>
            </el-table-column>
          </el-table>
          <div
            v-else
            class="empty-table"
          >
            <el-icon><Document /></el-icon><span>生成预测后，按月查看收入、成本、利润与计算依据。</span>
          </div>
          <div
            v-if="summary"
            class="table-note totals-note"
          >
            <span>全周期利润
              <b class="money">{{ formatMoney(summary.lifecycle_profit) }} 万元</b></span><span>期末借款 <b>{{ formatMoney(summary.ending_debt) }} 万元</b></span><span>期末应收 <b>{{ formatMoney(summary.ending_receivables) }} 万元</b></span>
          </div>
        </section>
      </div>
      <RunActivity
        :run="currentRun"
        :busy="busy"
        :poll-error="pollError"
        @resume="resume"
        @refresh="refreshStatus"
        @confirmed="refreshInputs"
      />
    </div>

    <el-drawer
      v-model="sensitivityOpen"
      title="情景与敏感性分析"
      size="min(860px, 95vw)"
    >
      <template v-if="result">
        <p class="drawer-lead">
          针对已保存运行
          {{ resultRun?.id.slice(0, 12) }}，下列金额由程序计算；单位：万元。
        </p>
        <h3>未来12个月 · 情景对比</h3>
        <div class="scenario-totals">
          <div
            v-for="(label, key) in scenarioLabels"
            :key="key"
          >
            <span>{{ label }}</span><b>{{ formatMoney(result.scenario_totals?.[key]) }}</b>
          </div>
        </div>
        <p class="drawer-note">
          情景范围反映假设变化，不是预测准确率或统计置信区间。
        </p>
        <h3>单因素敏感性</h3>
        <p class="drawer-note">
          利润比较未来12个月；资金缺口比较预测起始月至全周期末的峰值。缺口变化为正表示资金压力增加。
          项目汇总请进入绑定子项目查看敏感性，不相加各项目缺口峰值。旧运行未保存的分析列显示“—”。
        </p>
        <el-table
          :data="result.sensitivity"
          size="small"
          empty-text="该运行未保存单项目敏感性，请查看绑定子项目或创建新预测"
        >
          <el-table-column
            prop="label"
            label="调整因素"
            min-width="140"
          /><el-table-column
            label="12个月利润"
            align="right"
            width="125"
          >
            <template #default="{ row }">
              {{ formatMoney(row.profit) }}
            </template>
          </el-table-column><el-table-column
            label="利润变化"
            align="right"
            width="110"
          >
            <template #default="{ row }">
              <span :class="{ negative: Number(row.delta) < 0 }">{{ Number(row.delta) > 0 ? '+' : '' }}{{ formatMoney(row.delta) }}</span>
            </template>
          </el-table-column>
          <el-table-column
            label="资金缺口峰值"
            width="125"
            align="right"
          >
            <template #default="{ row }">
              {{ formatMoney(row.max_funding_gap) }}
            </template>
          </el-table-column>
          <el-table-column
            label="缺口变化"
            width="115"
            align="right"
          >
            <template #default="{ row }">
              <span :class="{ negative: Number(row.funding_gap_delta) > 0 }">{{ Number(row.funding_gap_delta) > 0 ? '+' : ''
              }}{{ formatMoney(row.funding_gap_delta) }}</span>
            </template>
          </el-table-column>
          <el-table-column
            label="状态"
            min-width="140"
          >
            <template #default="{ row }">
              {{
                row.error ? '不可计算：' + row.error : '已保存'
              }}
            </template>
          </el-table-column>
        </el-table>
        <p class="drawer-note">
          每次只改变一个因素。已签合同与历史实际不因未售调价、剩余成本调整而改写。
        </p>
        <RouterLink
          v-if="resultRun"
          :to="`/runs/${resultRun.id}`"
          class="quiet-link"
          @click="sensitivityOpen = false"
        >
          查看本次输入版本与运行记录
          <el-icon><ArrowRight /></el-icon>
        </RouterLink>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
.workbench-toolbar {
  display: flex;
  align-items: center;
  gap: 22px;
  margin: 0 0 14px;
  min-height: 35px;
}
.mode-control {
  display: flex;
  gap: 4px;
  padding: 3px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
}
.mode-control button {
  border: 0;
  border-radius: 5px;
  padding: 7px 13px;
  background: transparent;
  color: var(--muted);
  font-size: 12px;
  white-space: nowrap;
}
.mode-control .active {
  color: var(--accent);
  background: var(--soft);
  font-weight: 650;
}
.mode-control button span {
  font-size: 10px;
  padding: 1px 4px;
  background: var(--border);
  border-radius: 4px;
  margin-left: 4px;
}
.period-note {
  display: flex;
  gap: 7px;
  align-items: center;
  font-size: 11px;
  color: var(--muted);
}
.add-project {
  margin-left: auto;
}
.workbench-grid {
  display: grid;
  grid-template-columns: 250px minmax(0, 1fr) 295px;
  gap: 14px;
  align-items: start;
}
.results-column {
  display: flex;
  flex-direction: column;
  gap: 13px;
  min-width: 0;
}
.results-column .panel {
  padding: 18px;
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 15px;
}
.section-header > div {
  display: flex;
  align-items: baseline;
  gap: 12px;
  flex-wrap: wrap;
}
.section-header h2 {
  margin: 0;
  font-size: 17px;
  letter-spacing: -0.25px;
}
.section-caption {
  font-size: 10px;
  color: var(--muted);
}
.text-link {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  border: 0;
  background: none;
  padding: 3px 0;
  font-size: 11px;
  color: var(--accent);
  white-space: nowrap;
}
.text-link:disabled,
.sensitivity-button:disabled {
  cursor: default;
  color: var(--muted);
  opacity: 0.65;
}
.metrics-grid {
  display: grid;
  grid-template-columns: 1fr 1.13fr 1.2fr 1.07fr;
  gap: 9px;
}
.metric-card {
  background: linear-gradient(140deg, var(--soft), var(--solid));
  border: 1px solid var(--border);
  border-radius: 8px;
  min-width: 0;
  padding: 13px 12px;
  text-align: left;
  color: inherit;
}
.metric-card:disabled {
  cursor: default;
}
.metric-label {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}
.metric-label .el-icon {
  font-size: 20px;
  color: var(--accent);
  flex-shrink: 0;
}
.metric-card strong {
  display: block;
  margin: 10px 0 7px;
  font-size: clamp(18px, 1.45vw, 27px);
  line-height: 1.25;
  letter-spacing: -0.6px;
  white-space: nowrap;
}
.metric-card .range-value {
  font-size: clamp(15px, 1.18vw, 23px);
  letter-spacing: -0.65px;
}
.metric-foot {
  color: var(--muted);
  font-size: 9px;
  line-height: 1.5;
  display: block;
}
.gap-card strong,
.gap-card .el-icon {
  color: #a76926;
}
.result-version {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 8px;
  color: var(--muted);
  font-size: 10px;
  margin: -4px 0 12px;
}
.snapshot-caption {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 5px;
  color: var(--muted);
  font-size: 9px;
  margin-top: 11px;
}
.version-warning,
.validation-note {
  font-size: 11px;
  line-height: 1.7;
  color: #95652b;
  background: #fff7e9;
  padding: 8px 11px;
  border: 1px solid #efdfbf;
  border-radius: 6px;
  margin-bottom: 12px;
}
.workbench-alert {
  margin-bottom: 12px;
}
.workbench-alert p {
  font-size: 11px;
  margin-bottom: 0;
}
.chart-switch {
  display: flex;
  border: 1px solid var(--border);
  border-radius: 5px;
  overflow: hidden;
}
.chart-switch button {
  background: var(--solid);
  border: 0;
  color: var(--muted);
  padding: 6px 13px;
  font-size: 11px;
}
.chart-switch button.active {
  color: #fff;
  background: var(--accent);
}
.driver-strip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  border-top: 1px solid var(--border);
  padding-top: 14px;
  margin-top: 9px;
}
.driver-title {
  font-size: 12px;
  font-weight: 650;
  white-space: nowrap;
}
.driver-strip > div {
  display: flex;
  align-items: center;
  gap: 7px;
}
.driver-strip > div > .el-icon {
  color: var(--accent);
  font-size: 23px;
}
.driver-strip b {
  display: block;
  font-size: 11px;
  font-weight: 600;
}
.driver-strip small {
  display: block;
  font-size: 9px;
  color: var(--muted);
  margin-top: 4px;
}
.sensitivity-button {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 7px 8px;
  color: var(--accent);
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--solid);
  font-size: 10px;
  white-space: nowrap;
}
.forecast-empty {
  height: 285px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  background: linear-gradient(180deg, var(--solid), var(--soft));
  border-radius: 6px;
}
.empty-chart-icon {
  font-size: 36px;
  color: var(--accent);
  margin-bottom: 12px;
}
.forecast-empty h3 {
  margin: 0;
  font-size: 16px;
}
.forecast-empty p {
  color: var(--muted);
  font-size: 11px;
  margin: 12px 15px 9px;
}
.forecast-empty > span {
  font-size: 10px;
  color: var(--muted);
  margin-bottom: 18px;
}
.forecast-empty :deep(.el-button) {
  font-size: 12px;
}
.monthly-table,
.contribution-table {
  --el-table-header-bg-color: var(--soft);
  --el-table-row-hover-bg-color: var(--soft);
  --el-table-text-color: #334d71;
  --el-table-header-text-color: #314966;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-variant-numeric: tabular-nums;
}
.monthly-table :deep(.el-table__cell) {
  font-size: 11px;
  padding: 8px 0;
}
.monthly-table :deep(.cell) {
  padding: 0 8px;
}
.monthly-table :deep(td) {
  cursor: pointer;
}
.table-value {
  font-size: 11px;
  color: var(--accent);
  font-weight: 600;
  padding: 0;
  border: 0;
  background: none;
}
.period-chip {
  font-size: 9px;
  color: var(--accent);
  background: var(--soft);
  padding: 3px 5px;
  border-radius: 4px;
}
.period-chip.actual {
  color: #39796c;
  background: #ecf5f0;
}
.empty-table {
  height: 85px;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: var(--muted);
  border: 1px dashed var(--border);
  border-radius: 6px;
}
.table-note {
  font-size: 10px;
  color: var(--muted);
  line-height: 1.75;
  margin: 12px 0 0;
}
.totals-note {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
}
.totals-note b {
  font-weight: 550;
  color: #526782;
}
.incomplete-note {
  color: #976724;
  font-size: 11px;
  line-height: 1.7;
}
.negative {
  color: #b14b43 !important;
}
.drawer-lead {
  font-size: 12px;
  line-height: 1.8;
  color: var(--muted);
  margin-top: 0;
}
.drawer-note {
  font-size: 12px;
  line-height: 1.9;
  color: var(--muted);
  margin: 17px 0 25px;
}
.scenario-totals {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}
.scenario-totals div {
  display: flex;
  flex-direction: column;
  gap: 13px;
  padding: 17px;
  background: var(--soft);
  border-radius: 6px;
  font-size: 12px;
}
.scenario-totals b {
  font-size: 21px;
  font-variant-numeric: tabular-nums;
}
@media (min-width: 1700px) {
  .workbench-grid {
    grid-template-columns: 270px minmax(0, 1fr) 325px;
    gap: 17px;
  }
  .metric-label {
    font-size: 13px;
  }
  .metric-foot {
    font-size: 11px;
  }
  .section-header h2 {
    font-size: 19px;
  }
  .metric-card {
    padding: 15px;
  }
}
@media (max-width: 1300px) {
  .workbench-grid {
    grid-template-columns: 220px minmax(0, 1fr);
  }
  .workbench-grid > :last-child {
    grid-column: 1 / -1;
  }
  .metrics-grid {
    gap: 7px;
  }
  .period-note {
    font-size: 10px;
  }
}
</style>
