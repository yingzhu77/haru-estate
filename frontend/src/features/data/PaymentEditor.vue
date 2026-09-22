<script setup lang="ts">
import type { components } from "../../api/schema";
type Payment = components["schemas"]["Payment"];
const props = defineProps<{ modelValue: Payment[]; label: string }>();
const emit = defineEmits<{ "update:modelValue": [value: Payment[]] }>();
function update(index: number, key: keyof Payment, value: string) {
  emit(
    "update:modelValue",
    props.modelValue.map((p, i) => (i === index ? { ...p, [key]: value } : p)),
  );
}
</script>
<template>
  <div class="payments">
    <div class="toolbar">
      <strong>{{ label }}</strong><el-button
        size="small"
        @click="
          emit('update:modelValue', [...modelValue, { month: '', amount: '' }])
        "
      >
        添加节点
      </el-button>
    </div>
    <p
      v-if="!modelValue.length"
      class="muted"
    >
      未配置节点。保存前请核对模型规则，不会将空金额补成零。
    </p>
    <div
      v-for="(payment, index) in modelValue"
      :key="index"
      class="payment-row"
    >
      <label>月份
        <input
          :value="payment.month"
          type="month"
          :aria-label="label + '月份'"
          @input="
            update(index, 'month', ($event.target as HTMLInputElement).value)
          "
        ></label>
      <label>金额（元）<input
        :value="payment.amount"
        inputmode="decimal"
        :aria-label="label + '金额'"
        @input="
          update(index, 'amount', ($event.target as HTMLInputElement).value)
        "
      ></label>
      <el-button
        type="danger"
        link
        @click="
          emit(
            'update:modelValue',
            modelValue.filter((_, i) => i !== index),
          )
        "
      >
        删除节点
      </el-button>
    </div>
  </div>
</template>
<style scoped>
.payments {
  padding: 16px;
  background: var(--soft);
  border-radius: 8px;
  margin-top: 14px;
}
.payments .toolbar {
  margin-bottom: 8px;
}
.payments p {
  font-size: 12px;
}
.payment-row {
  display: flex;
  gap: 16px;
  align-items: center;
  margin: 8px 0;
}
.payment-row label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}
input {
  border: 1px solid var(--border);
  background: var(--solid);
  border-radius: 6px;
  padding: 7px;
  color: inherit;
  width: 180px;
}
</style>
