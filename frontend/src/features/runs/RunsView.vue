<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api } from '../../api/client'
import type { Comparison, Run } from '../../api/types'
import { formatMoney, showEvidence, state } from '../../state'
import { runLabels, scenarioLabels } from '../data/editor'
const runs = ref<Run[]>([])
const kind = ref<'all' | 'project' | 'portfolio'>('all')
const projectId = ref('')
const loading = ref(false)
const error = ref('')
const left = ref('')
const right = ref('')
const comparison = ref<Comparison | null>(null)
const offset = ref(0)
const total = ref(0)
const selectedRuns = ref<Run[]>([])
const comparing = ref(false)
let loadGeneration = 0
let compareGeneration = 0
const comparable = computed(() => [
  ...new Map(
    [...selectedRuns.value, ...runs.value]
      .filter((run) => !!run.result)
      .map((run) => [run.id, run]),
  ).values(),
])
const rows = computed(() =>
  comparison.value
    ? [
        ...(comparison.value.bridge ?? []),
        ...(comparison.value.total_bridge ? [comparison.value.total_bridge] : []),
      ]
    : [],
)
const bridgeColumns = [
  { key: 'revenue', label: '收入贡献' },
  { key: 'cogs', label: '成本贡献' },
  { key: 'expenses', label: '费用贡献' },
  { key: 'taxes', label: '税费贡献' },
  { key: 'interest', label: '利息贡献' },
  { key: 'profit', label: '利润变化' },
] as const
function label(run: Run) {
  return run.project_names.join('、') + ' / ' + run.forecast_origin + ' / ' + run.id.slice(0, 8)
}
async function load() {
  const generation = ++loadGeneration
  loading.value = true
  runs.value = []
  error.value = ''
  try {
    const result = await api.runPage({
      projectId: projectId.value || undefined,
      kind: kind.value === 'all' ? undefined : kind.value,
      offset: offset.value,
      limit: 20,
    })
    if (generation !== loadGeneration) return
    runs.value = result.items
    total.value = result.total
  } catch (e) {
    if (generation === loadGeneration) error.value = e instanceof Error ? e.message : String(e)
  } finally {
    if (generation === loadGeneration) loading.value = false
  }
}
function turn(delta: number) {
  offset.value += delta * 20
  void load()
}
watch([kind, projectId], () => {
  offset.value = 0
  runs.value = []
  total.value = 0
  void load()
})
watch([left, right], () => {
  selectedRuns.value = comparable.value.filter((run) => [left.value, right.value].includes(run.id))
  ++compareGeneration
  comparing.value = false
  comparison.value = null
})
async function compare() {
  if (!left.value || !right.value || left.value === right.value) {
    error.value = '请选择两次不同的已完成预测'
    return
  }
  const generation = ++compareGeneration
  comparing.value = true
  error.value = ''
  comparison.value = null
  try {
    const result = await api.compare(left.value, right.value)
    if (generation === compareGeneration) comparison.value = result
  } catch (e) {
    if (generation === compareGeneration) error.value = e instanceof Error ? e.message : String(e)
  } finally {
    if (generation === compareGeneration) comparing.value = false
  }
}
onMounted(load)
onBeforeUnmount(() => {
  ++loadGeneration
  ++compareGeneration
})
</script>
<template>
  <div class="page-heading">
    <div>
      <h1>历史预测</h1>
      <p class="muted">
        保存每一次预测的时点、输入版本与执行过程。
      </p>
    </div>
    <el-button
      :loading="loading"
      @click="load"
    >
      刷新记录
    </el-button>
  </div>
  <el-alert
    v-if="error"
    :title="error"
    type="error"
    :closable="false"
  />
  <section class="panel">
    <div class="toolbar">
      <el-radio-group v-model="kind">
        <el-radio-button value="all">
          全部
        </el-radio-button><el-radio-button value="project">
          单项目
        </el-radio-button><el-radio-button value="portfolio">
          项目汇总
        </el-radio-button>
      </el-radio-group><el-select
        v-model="projectId"
        aria-label="历史项目筛选"
        clearable
        placeholder="按成员项目筛选"
        style="width: 260px"
      >
        <el-option
          v-for="project in state.projects"
          :key="project.id"
          :label="project.name"
          :value="project.id"
        />
      </el-select>
    </div>
    <el-table
      v-loading="loading"
      :data="runs"
      row-key="id"
      empty-text="暂无运行，请先到工作台创建预测"
    >
      <el-table-column
        label="运行 / 项目"
        min-width="230"
      >
        <template #default="{ row }">
          <RouterLink :to="'/runs/' + row.id">
            {{ row.project_names.join('、') || '未命名项目' }}
          </RouterLink><small class="muted run-id">{{ row.id }}</small>
        </template>
      </el-table-column>
      <el-table-column
        label="类型"
        width="100"
      >
        <template #default="{ row }">
          {{ row.kind === 'portfolio' ? '项目汇总' : '单项目' }}
        </template>
      </el-table-column>
      <el-table-column
        prop="forecast_origin"
        label="预测基准日"
        width="125"
      />
      <el-table-column
        prop="information_cutoff"
        label="信息截止"
        width="125"
      />
      <el-table-column
        label="情景"
        width="80"
      >
        <template #default="{ row }">
          {{ scenarioLabels[row.scenario] }}
        </template>
      </el-table-column>
      <el-table-column
        label="状态"
        width="120"
      >
        <template #default="{ row }">
          <el-tag :type="row.result ? 'success' : row.error ? 'danger' : 'info'">
            {{ runLabels[row.status] ?? row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column
        label="12月利润（万元）"
        width="170"
        align="right"
      >
        <template #default="{ row }">
          {{ formatMoney(row.result?.summary.twelve_month_profit) }}
        </template>
      </el-table-column>
      <el-table-column
        label="生成时间"
        min-width="160"
      >
        <template #default="{ row }">
          {{ row.created_at.replace('T', ' ').slice(0, 19) }}
        </template>
      </el-table-column>
    </el-table>
    <div class="toolbar pagination">
      <el-button
        :disabled="loading || !offset"
        @click="turn(-1)"
      >
        上一页预测
      </el-button>
      <span>第 {{ Math.floor(offset / 20) + 1 }} 页 · 共 {{ total }} 条</span>
      <el-button
        :disabled="loading || offset + 20 >= total"
        @click="turn(1)"
      >
        下一页预测
      </el-button>
    </div>
  </section>
  <section class="panel compare-panel">
    <h2>对齐目标月份比较</h2>
    <p class="muted">
      只比较共同月份、相同币种和利润口径；不同预测窗口的累计值不能直接视为经营变化。
    </p>
    <div class="toolbar">
      <el-select
        v-model="left"
        aria-label="原预测"
        placeholder="原预测"
        style="width: 340px"
      >
        <el-option
          v-for="run in comparable"
          :key="run.id"
          :value="run.id"
          :label="label(run)"
        />
      </el-select><span>→</span><el-select
        v-model="right"
        aria-label="对照预测"
        placeholder="对照预测"
        style="width: 340px"
      >
        <el-option
          v-for="run in comparable"
          :key="run.id"
          :value="run.id"
          :label="label(run)"
        />
      </el-select><el-button
        type="primary"
        :loading="comparing"
        @click="compare"
      >
        比较共同月份
      </el-button>
    </div>
    <template v-if="comparison">
      <p class="muted">
        下表为程序按利润组成项计算的差额分解，不代表因果归因。收入增加为正贡献，成本和费用增加为负贡献；单位：万元。比较只覆盖共同月份。
      </p>
      <div class="toolbar">
        <el-button @click="showEvidence(comparison.left_id, 'twelve_month_profit')">
          查看原预测来源
        </el-button>
        <el-button @click="showEvidence(comparison.right_id, 'twelve_month_profit')">
          查看对照预测来源
        </el-button>
      </div>
      <el-alert
        v-if="comparison.membership_changed"
        title="成员范围发生变化，利润差额同时包含项目范围变化，不能全部解释为经营改善。"
        type="warning"
        :closable="false"
      /><el-table
        :data="rows"
        empty-text="两次预测没有共同目标月份"
      >
        <el-table-column
          prop="month"
          label="目标月份"
        /><el-table-column
          v-for="column in bridgeColumns"
          :key="column.key"
          :label="column.label"
          align="right"
          min-width="100"
        >
          <template #default="{ row }">
            {{ formatMoney(row[column.key]) }}
          </template>
        </el-table-column>
        <el-table-column
          label="当月来源"
          min-width="150"
        >
          <template #default="{ row }">
            <template v-if="comparison.months.includes(row.month)">
              <el-button
                link
                @click="showEvidence(comparison.left_id, 'profit', row.month)"
              >
                原预测
              </el-button>
              <el-button
                link
                @click="showEvidence(comparison.right_id, 'profit', row.month)"
              >
                对照
              </el-button>
            </template>
          </template>
        </el-table-column>
      </el-table>
    </template>
  </section>
</template>
<style scoped>
.run-id {
  display: block;
  font-size: 10px;
  line-height: 1.8;
}
.compare-panel {
  margin-top: 18px;
}
.pagination {
  margin-top: 16px;
}
.compare-panel p {
  font-size: 12px;
}
</style>
