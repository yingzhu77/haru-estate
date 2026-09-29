<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { api } from '../../api/client'
import type { RevisionComparison, RevisionPage } from '../../api/types'

const props = defineProps<{ projectId: string; revisionId: string }>()
const page = ref<RevisionPage | null>(null)
const offset = ref(0)
const loading = ref(false)
const error = ref('')
const left = ref('')
const right = ref('')
const comparison = ref<RevisionComparison | null>(null)
const choices = ref<RevisionPage['items']>([])
const recordNames = ref<Record<string, string>>({})
const pageNumber = computed(() => Math.floor(offset.value / 10) + 1)
const chosen = computed(() => new Map(choices.value.map((item) => [item.id, item])))
let generation = 0
let compareGeneration = 0

async function load() {
  const token = ++generation
  const id = props.projectId
  loading.value = true
  page.value = null
  error.value = ''
  try {
    const result = await api.revisions(id, offset.value, 10)
    if (token !== generation) return
    page.value = result
    const retained = choices.value.filter((item) => [left.value, right.value].includes(item.id))
    choices.value = [
      ...new Map([...retained, ...result.items].map((item) => [item.id, item])).values(),
    ]
    if (!right.value) right.value = result.items[0]?.id ?? ''
    if (!left.value) left.value = result.items[1]?.id ?? ''
  } catch (cause) {
    if (token === generation) error.value = cause instanceof Error ? cause.message : String(cause)
  } finally {
    if (token === generation) loading.value = false
  }
}
async function compare() {
  const token = ++compareGeneration
  comparison.value = null
  error.value = ''
  try {
    const [result, snapshots] = await Promise.all([
      api.compareRevisions(props.projectId, left.value, right.value),
      Promise.allSettled([
        api.input(props.projectId, left.value),
        api.input(props.projectId, right.value),
      ]),
    ])
    if (token !== compareGeneration) return
    comparison.value = result
    const revisions = snapshots.flatMap((snapshot) =>
      snapshot.status === 'fulfilled' ? [snapshot.value] : [],
    )
    recordNames.value = Object.fromEntries(
      revisions.flatMap((revision) => revision.data.phases ?? []).map((phase) => [
        phase.id,
        `${phase.name}（分期）`,
      ]),
    )
  } catch (cause) {
    if (token === compareGeneration)
      error.value = cause instanceof Error ? cause.message : String(cause)
  }
}
function turn(delta: number) {
  offset.value += delta * 10
  void load()
}
watch(
  () => [props.projectId, props.revisionId] as const,
  ([projectId, revisionId], previous) => {
    ++compareGeneration
    offset.value = 0
    if (!previous || projectId !== previous[0]) {
      left.value = right.value = ''
      choices.value = []
    } else {
      left.value = previous[1]
      right.value = revisionId
    }
    page.value = null
    comparison.value = null
    void load()
  },
  { immediate: true },
)
watch([left, right], () => {
  ++compareGeneration
  comparison.value = null
})
onBeforeUnmount(() => {
  ++generation
  ++compareGeneration
})
const labels: Record<string, string> = {
  data: '输入',
  phases: '分期计划',
  contracts: '销售合同',
  costs: '开发成本',
  actuals: '历史实际',
  assumptions: '测算假设',
  price: '未售单价',
  amount: '金额',
  area: '面积',
  known_on: '获知日',
  delivery_month: '交付月',
  collections: '回款安排',
  payments: '付款安排',
  actual_closed_through: '实际结账月',
  monthly_overhead: '月度费用',
  opening_cash: '期初现金',
}
function pathLabel(path: string) {
  return path
    .split('/')
    .map((part) => labels[part] ?? recordNames.value[part] ?? part)
    .join(' / ')
}
function monthDifference(before: string | null, after: string | null) {
  if (!before || !after || !/^\d{4}-\d{2}$/.test(before) || !/^\d{4}-\d{2}$/.test(after))
    return null
  const [beforeYear, beforeMonth] = before.split('-').map(Number)
  const [afterYear, afterMonth] = after.split('-').map(Number)
  return (afterYear - beforeYear) * 12 + afterMonth - beforeMonth
}
function businessMeaning(row: RevisionComparison['changes'][number]) {
  const field = row.path.split('/').at(-1)
  if (field === 'delivery_month') {
    const months = monthDifference(row.before, row.after)
    if (months && months > 0) return `交付计划延后 ${months} 个月；需重新生成预测后查看利润和现金影响。`
    if (months && months < 0) return `交付计划提前 ${Math.abs(months)} 个月；需重新生成预测后查看利润和现金影响。`
    return '交付计划已调整；需重新生成预测后查看利润和现金影响。'
  }
  if (field === 'known_on')
    return `从 ${row.after ?? '该日期'} 起，这项新版计划才能用于预测；更早的预测仍保留原计划。`
  return '这是输入参数的版本差异；已保存预测不会被改写。'
}
</script>

<template>
  <section class="panel revision-history">
    <div class="toolbar">
      <h2>输入版本与差异</h2>
      <el-button
        :loading="loading"
        @click="load"
      >
        刷新版本
      </el-button>
    </div>
    <p class="muted">
      只读回看，不覆盖当前草稿。先选调整前、调整后版本，再查看这次变化对新预测意味着什么。
    </p>
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      :closable="false"
    />
    <el-table
      v-loading="loading"
      :data="page?.items ?? []"
      row-key="id"
    >
      <el-table-column
        prop="version"
        label="版本"
        width="80"
      />
      <el-table-column
        prop="known_on"
        label="信息获知日"
        width="130"
      />
      <el-table-column
        prop="note"
        label="修订说明"
        min-width="160"
      />
      <el-table-column
        prop="id"
        label="版本编号"
        min-width="250"
      />
    </el-table>
    <div class="toolbar pagination">
      <el-button
        :disabled="loading || !offset"
        @click="turn(-1)"
      >
        上一页版本
      </el-button>
      <span>第 {{ pageNumber }} 页 · 共 {{ page?.total ?? 0 }} 个版本</span>
      <el-button
        :disabled="loading || offset + 10 >= (page?.total ?? 0)"
        @click="turn(1)"
      >
        下一页版本
      </el-button>
    </div>
    <div class="toolbar">
      <el-select
        v-model="left"
        placeholder="原输入版本"
        aria-label="原输入版本"
      >
        <el-option
          v-for="item in choices"
          :key="item.id"
          :label="`V${item.version} · ${item.known_on}`"
          :value="item.id"
        />
      </el-select>
      <span>→</span>
      <el-select
        v-model="right"
        placeholder="对照输入版本"
        aria-label="对照输入版本"
      >
        <el-option
          v-for="item in choices"
          :key="item.id"
          :label="`V${item.version} · ${item.known_on}`"
          :value="item.id"
        />
      </el-select>
      <el-button
        :disabled="!left || !right || left === right"
        @click="compare"
      >
        查看输入差异
      </el-button>
    </div>
    <el-table
      v-if="comparison"
      :data="comparison.changes"
      empty-text="业务输入未变化；获知日和说明请查看版本列表"
    >
      <template #append>
        <p class="comparison-note">
          对比版本：v{{ chosen.get(left)?.version ?? '—' }} → v{{ chosen.get(right)?.version ?? '—' }}。这里是输入计划的变化，不是已经计算出的利润或现金变化。
        </p>
      </template>
      <el-table-column
        label="调整对象"
        min-width="210"
      >
        <template #default="{ row }">
          {{ pathLabel(row.path) }}
        </template>
      </el-table-column>
      <el-table-column
        label="调整类型"
        width="75"
      >
        <template #default="{ row }">
          {{
            { added: '新增', removed: '移除', changed: '修改' }[
              row.kind as 'added' | 'removed' | 'changed'
            ]
          }}
        </template>
      </el-table-column>
      <el-table-column
        :label="`调整前（v${chosen.get(left)?.version ?? '—'}）`"
        min-width="190"
      >
        <template #default="{ row }">
          <span class="diff-value">{{ row.before ?? '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column
        :label="`调整后（v${chosen.get(right)?.version ?? '—'}）`"
        min-width="190"
      >
        <template #default="{ row }">
          <span class="diff-value">{{ row.after ?? '—' }}</span>
        </template>
      </el-table-column>
      <el-table-column
        label="这意味着什么"
        min-width="270"
      >
        <template #default="{ row }">
          {{ businessMeaning(row) }}
        </template>
      </el-table-column>
    </el-table>
  </section>
</template>

<style scoped>
.revision-history {
  margin-top: 18px;
}
.revision-history p {
  font-size: 12px;
}
.revision-history .el-select {
  width: 230px;
}
.pagination {
  margin: 16px 0;
}
.diff-value {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.comparison-note {
  padding: 10px 12px;
  margin: 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.7;
}
</style>
