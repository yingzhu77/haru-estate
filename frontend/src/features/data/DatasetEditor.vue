<script setup lang="ts">
import { ref } from 'vue'
import type { Dataset } from '../../api/types'
import { cloneData, collectionFields, assumptionFields, metricLabels, phaseReferenced, type EditorField } from './editor'
import PaymentEditor from './PaymentEditor.vue'
const props = defineProps<{ modelValue: Dataset; knownOn: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: Dataset] }>()
type Collection = keyof typeof collectionFields
type Payment = { month: string; amount: string }
const error = ref('')
const titles: Record<Collection, string> = { phases: '分期与销售计划', contracts: '已签合同与回款', costs: '成本与付款计划', actuals: '历史实际' }
function fieldValue(row: object, key: string) { return (row as Record<string, string | number | null>)[key] ?? '' }
function change(collection: Collection, index: number, field: EditorField, value: string) {
  const data = cloneData(props.modelValue)
  const rows = data[collection] as unknown as Record<string, unknown>[]
  const row = rows[index]
  if (!row) return
  row[field.key] = field.type === 'number' ? Number(value) : (field.key === 'recognized_month' || field.key === 'contract_id') && !value ? null : value
  emit('update:modelValue', data)
}
function changeAssumption(field: EditorField, value: string) {
  const data = cloneData(props.modelValue)
  const assumptions = data.assumptions as unknown as Record<string, unknown>
  assumptions[field.key] = field.type === 'number' ? Number(value) : value
  emit('update:modelValue', data)
}
function add(collection: Collection) {
  const data = cloneData(props.modelValue)
  const id = crypto.randomUUID()
  const phase_id = data.phases?.[0]?.id ?? ''
  if (collection === 'phases') data.phases = [...(data.phases ?? []), { id, name: '', area: '', price: '', sales_start: '', sales_months: 6, delivery_month: '', known_on: props.knownOn }]
  if (collection === 'contracts') data.contracts = [...(data.contracts ?? []), { id, phase_id, sale_month: '', area: '', amount: '', known_on: props.knownOn, recognized_month: null, collections: [] }]
  if (collection === 'costs') data.costs = [...(data.costs ?? []), { id, phase_id, category: 'construction', amount: '', incurred_month: '', known_on: props.knownOn, payments: [] }]
  if (collection === 'actuals') data.actuals = [...(data.actuals ?? []), { id, phase_id, month: '', known_on: props.knownOn, metric: 'revenue', amount: '', note: '' }]
  emit('update:modelValue', data)
}
function remove(collection: Collection, index: number) {
  error.value = ''
  if (collection === 'phases' && phaseReferenced(props.modelValue, props.modelValue.phases?.[index]?.id ?? '')) {
    error.value = '该分期仍被合同、成本或实际记录引用，请先调整这些记录。'; return
  }
  const data = cloneData(props.modelValue)
  data[collection]?.splice(index, 1)
  emit('update:modelValue', data)
}
function payments(row: object, key: string): Payment[] { return (row as Record<string, Payment[]>)[key] ?? [] }
function changePayments(collection: Collection, index: number, key: string, value: Payment[]) {
  const data = cloneData(props.modelValue)
  const row = data[collection]?.[index] as unknown as Record<string, unknown>
  row[key] = value; emit('update:modelValue', data)
}
function changeLoans(key: 'loan_draws' | 'loan_repayments', value: Payment[]) {
  const data = cloneData(props.modelValue)
  data.assumptions[key] = value; emit('update:modelValue', data)
}
</script>
<template>
  <el-alert v-if="error" :title="error" type="warning" :closable="false" />
  <el-tabs>
    <el-tab-pane v-for="(fields, collection) in collectionFields" :key="collection" :label="titles[collection] + ' · ' + (modelValue[collection]?.length ?? 0)">
      <div class="toolbar"><el-button type="primary" plain @click="add(collection)">添加{{ collection === 'phases' ? '分期' : '记录' }}</el-button><span class="muted">金额使用元，比例使用小数；所有改动保存后才形成新版本。</span></div>
      <el-empty v-if="!modelValue[collection]?.length" description="尚无记录，缺项不会自动补零" :image-size="60" />
      <article v-for="(row, index) in modelValue[collection]" :key="index" class="record">
        <div class="record-heading"><strong>{{ titles[collection] }} #{{ index + 1 }}</strong><el-button type="danger" link @click="remove(collection, index)">移除草稿记录</el-button></div>
        <div class="field-grid">
          <label v-for="field in fields" :key="field.key">
            <span>{{ field.label }}</span>
            <select v-if="field.type === 'phase'" :value="fieldValue(row, field.key)" @change="change(collection, index, field, ($event.target as HTMLSelectElement).value)"><option value="">请选择分期</option><option v-for="phase in modelValue.phases" :key="phase.id" :value="phase.id">{{ phase.name || phase.id }}</option></select>
            <select v-else-if="field.type === 'category'" :value="fieldValue(row, field.key)" @change="change(collection, index, field, ($event.target as HTMLSelectElement).value)"><option value="land">土地</option><option value="construction">建安</option><option value="other">其他</option></select>
            <select v-else-if="field.type === 'metric'" :value="fieldValue(row, field.key)" @change="change(collection, index, field, ($event.target as HTMLSelectElement).value)"><option v-for="(label, key) in metricLabels" :key="key" :value="key">{{ label }}</option></select>
            <input v-else :value="fieldValue(row, field.key)" :type="field.type ?? 'text'" :aria-label="field.label" :readonly="collection === 'phases' && field.key === 'id'" @input="change(collection, index, field, ($event.target as HTMLInputElement).value)">
          </label>
        </div>
        <PaymentEditor v-if="collection === 'contracts'" :model-value="payments(row, 'collections')" label="合同回款节点" @update:model-value="changePayments(collection, index, 'collections', $event)" />
        <PaymentEditor v-if="collection === 'costs'" :model-value="payments(row, 'payments')" label="成本付款节点" @update:model-value="changePayments(collection, index, 'payments', $event)" />
      </article>
    </el-tab-pane>
    <el-tab-pane label="经营与融资假设">
      <el-alert title="以下参数均为模拟假设，待业务调研确认。融资提款与还本按明确节点配置。" type="info" :closable="false" />
      <div class="field-grid assumption-grid"><label v-for="field in assumptionFields" :key="field.key"><span>{{ field.label }}</span><input :value="fieldValue(modelValue.assumptions, field.key)" :type="field.type ?? 'text'" :aria-label="field.label" @input="changeAssumption(field, ($event.target as HTMLInputElement).value)"></label></div>
      <PaymentEditor :model-value="modelValue.assumptions.loan_draws ?? []" label="融资提款计划" @update:model-value="changeLoans('loan_draws', $event)" />
      <PaymentEditor :model-value="modelValue.assumptions.loan_repayments ?? []" label="融资还本计划" @update:model-value="changeLoans('loan_repayments', $event)" />
    </el-tab-pane>
  </el-tabs>
</template>
<style scoped>
.record{border:1px solid var(--border);border-radius:8px;padding:18px;background:var(--solid);margin-bottom:16px}.record-heading{display:flex;justify-content:space-between;margin-bottom:14px}.field-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.field-grid label{display:flex;flex-direction:column;gap:7px;font-size:12px}.field-grid input,.field-grid select{width:100%;height:36px;border:1px solid var(--border);border-radius:6px;background:var(--solid);color:inherit;padding:6px 8px}.field-grid input[readonly]{background:var(--soft);font-size:11px}.assumption-grid{margin-top:20px}.toolbar .muted{font-size:12px}@media(max-width:1250px){.field-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}
</style>
