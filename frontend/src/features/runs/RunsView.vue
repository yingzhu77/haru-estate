<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../../api/client'
import type { Comparison, Run } from '../../api/types'
import { formatMoney, state } from '../../state'
import { runLabels, scenarioLabels } from '../data/editor'
const runs = ref<Run[]>([])
const kind = ref('all')
const projectId = ref('')
const loading = ref(false)
const error = ref('')
const left = ref('')
const right = ref('')
const comparison = ref<Comparison | null>(null)
const visible = computed(() =>
  runs.value.filter(
    (run) =>
      (kind.value === 'all' || run.kind === kind.value) &&
      (!projectId.value || run.project_ids.includes(projectId.value)),
  ),
)
const comparable = computed(() => runs.value.filter((run) => !!run.result))
const rows = computed(
  () =>
    comparison.value?.months.map((month, index) => ({
      month,
      delta: comparison.value?.profit_deltas[index],
    })) ?? [],
)
function label(run: Run) {
  return run.project_names.join('、') + ' / ' + run.forecast_origin + ' / ' + run.id.slice(0, 8)
}
async function load() {
  loading.value = true
  error.value = ''
  try {
    runs.value = await api.runs()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}
async function compare() {
  if (!left.value || !right.value || left.value === right.value) {
    error.value = '请选择两次不同的已完成预测'
    return
  }
  loading.value = true
  error.value = ''
  comparison.value = null
  try {
    comparison.value = await api.compare(left.value, right.value)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}
onMounted(load)
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
      :data="visible"
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
  </section>
  <section class="panel compare-panel">
    <h2>对齐目标月份比较</h2>
    <p class="muted">
      只比较共同月份、相同币种和利润口径；不同预测窗口的累计值不能直接视为经营变化。
    </p>
    <div class="toolbar">
      <el-select
        v-model="left"
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
        :loading="loading"
        @click="compare"
      >
        比较共同月份
      </el-button>
    </div>
    <template v-if="comparison">
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
        /><el-table-column label="对照减原预测 · 利润变化（万元）">
          <template #default="{ row }">
            {{ formatMoney(row.delta) }}
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
.compare-panel p {
  font-size: 12px;
}
</style>
