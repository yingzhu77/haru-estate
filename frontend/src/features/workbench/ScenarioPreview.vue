<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import { api } from '../../api/client'
import type { EffectiveParameters, RunCreate } from '../../api/types'
import { state } from '../../state'
import { defaultOverrides } from './useWorkbench'

const props = defineProps<{ scenario: RunCreate['scenario']; revisionId?: string }>()
const items = ref<EffectiveParameters[]>([])
const loading = ref(false)
const error = ref('')
let sequence = 0
let timer: ReturnType<typeof setTimeout> | undefined
const input = computed(() => {
  const ids = state.mode === 'project' ? [state.selectedProjectId] : state.selectedProjectIds
  return {
    kind: state.mode,
    project_ids: ids.filter(Boolean),
    forecast_origin: state.forecastOrigin,
    information_cutoff: state.informationCutoff,
    scenario: props.scenario,
    overrides: Object.fromEntries(ids.map((id) => [id, state.overrides[id] ?? defaultOverrides()])),
  }
})
watch(
  () => [input.value, props.revisionId],
  () => {
    const current = ++sequence
    clearTimeout(timer)
    items.value = []
    error.value = ''
    loading.value = input.value.project_ids.length > 0
    if (!loading.value) return
    const body = JSON.parse(JSON.stringify(input.value)) as RunCreate
    timer = setTimeout(async () => {
      try {
        const result = await api.parameterPreview(body)
        if (sequence === current) items.value = result
      } catch (reason) {
        if (sequence === current)
          error.value = reason instanceof Error ? reason.message : '参数预览暂不可用'
      } finally {
        if (sequence === current) loading.value = false
      }
    }, 180)
  },
  { deep: true, immediate: true },
)
onBeforeUnmount(() => {
  ++sequence
  clearTimeout(timer)
})
const number = (value: string) =>
  Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
const percent = (value: string) => `${Number(value) > 0 ? '+' : ''}${number(value)}%`
</script>

<template>
  <section
    class="scenario-preview"
    aria-label="情景有效参数"
    aria-live="polite"
  >
    <h3>本情景调整项</h3>
    <p v-if="loading">
      正在按信息截止日期读取参数…
    </p>
    <p
      v-else-if="error"
      role="alert"
    >
      {{ error }}
    </p>
    <p v-else-if="!items.length">
      选择项目后查看。
    </p>
    <p v-if="items[0]">
      未售售价 {{ percent(items[0].scenario_price_percent) }} · 未来成本
      {{ percent(items[0].scenario_cost_percent) }}
    </p>
    <h3>叠加后的有效参数</h3>
    <article
      v-for="item in items"
      :key="item.project_id"
    >
      <b>{{ item.project_name }} · 输入 v{{ item.version }}</b>
      <p>未售售价 {{ percent(item.price_percent) }} · 未来成本 {{ percent(item.cost_percent) }}</p>
      <dl
        v-for="phase in item.phases"
        :key="phase.id"
      >
        <dt>{{ phase.name }} · 单价（元/㎡）</dt>
        <dd>
          {{ number(phase.original_price) }} → <strong>{{ number(phase.effective_price) }}</strong>
        </dd>
        <dt>交付月份</dt>
        <dd>{{ phase.original_delivery }} → {{ phase.effective_delivery }}</dd>
      </dl>
      <details>
        <summary>成本、回款与适用边界</summary>
        <p v-if="item.future_cost_before !== null && item.future_cost_after !== null">
          未来成本合计（元）：{{ number(item.future_cost_before) }} →
          {{ number(item.future_cost_after) }}
        </p>
        <p>
          新销售尾款滞后 {{ item.collection_lag }} 月；合同未来回款额外延后
          {{ item.extra_collection_delay }} 月。首付不随尾款延期。
        </p>
        <p
          v-for="warning in item.warnings"
          :key="warning"
        >
          {{ warning }}
        </p>
      </details>
    </article>
    <p class="note">
      草稿预览，采用信息截止前可用的输入版本。手动调整与情景预设相乘叠加；点击生成后才创建预测。已签金额和历史成本保持原值。
    </p>
    <details>
      <summary>这些词是什么意思？</summary>
      <p>
        基准：按当前计划；乐观：售价较高、未来成本较低；审慎：售价较低、未来成本较高。三种都是模拟假设，待业务调研确认，并非发生概率。
      </p>
      <p>
        销售是签约，回款是钱到账，收入确认是按交付规则计入收入；成本结转是把已交付部分对应的开发成本计入利润扣减。利润与现金余额不是一回事。
      </p>
    </details>
  </section>
</template>

<style scoped>
.scenario-preview {
  margin-top: 14px;
  padding: 12px;
  background: var(--soft);
  border: 1px solid var(--border);
  border-radius: 7px;
  font-size: 12px;
  line-height: 1.65;
  overflow-wrap: anywhere;
}
h3 {
  margin: 0 0 6px;
  font-size: 13px;
}
h3:not(:first-child) {
  margin-top: 14px;
}
p {
  margin: 6px 0;
}
article + article {
  border-top: 1px solid var(--border);
  margin-top: 12px;
  padding-top: 12px;
}
dl {
  margin: 8px 0;
}
dt,
.note {
  color: var(--muted);
}
dd {
  margin: 0;
  font-variant-numeric: tabular-nums;
}
strong {
  color: var(--accent);
}
summary {
  cursor: pointer;
}
details {
  margin-top: 8px;
}
</style>
