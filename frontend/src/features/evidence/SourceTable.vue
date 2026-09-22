<script setup lang="ts">
import type { Source } from "../../api/types";
import { formatMoney } from "../../state";
import { metricLabels } from "../data/editor";
defineProps<{ sources: Source[] }>();
function label(metric: string) {
  return metricLabels[metric as keyof typeof metricLabels] ?? metric;
}
</script>
<template>
  <el-table
    :data="sources"
    size="small"
    max-height="460"
  >
    <el-table-column
      prop="month"
      label="月份"
      width="90"
    />
    <el-table-column
      label="科目"
      min-width="95"
    >
      <template #default="{ row }">
        {{
          label(row.metric)
        }}
      </template>
    </el-table-column>
    <el-table-column
      label="金额（万元）"
      align="right"
      width="130"
    >
      <template #default="{ row }">
        {{
          formatMoney(row.amount)
        }}
      </template>
    </el-table-column>
    <el-table-column
      prop="record_id"
      label="原记录编号"
      min-width="155"
      show-overflow-tooltip
    />
    <el-table-column
      prop="phase_id"
      label="分期"
      min-width="100"
      show-overflow-tooltip
    />
    <el-table-column
      prop="rule"
      label="规则"
      min-width="140"
    />
    <el-table-column
      prop="description"
      label="计算依据"
      min-width="230"
    />
  </el-table>
</template>
