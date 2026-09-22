<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { api } from "../../api/client";
import type { Evidence } from "../../api/types";
import { formatMoney, state } from "../../state";
import { runLabels } from "../data/editor";
import SourceTable from "./SourceTable.vue";
type Selection = NonNullable<typeof state.evidence>;
const evidence = ref<Evidence | null>(null);
const loading = ref(false);
const error = ref("");
const trail = ref<Selection[]>([]);
const open = computed({
  get: () => !!state.evidence,
  set: (value) => {
    if (!value) {
      state.evidence = null;
      trail.value = [];
    }
  },
});
let requestSequence = 0;
let navigating = false;
watch(
  () => state.evidence,
  async (selection) => {
    const sequence = ++requestSequence;
    if (!navigating) trail.value = [];
    navigating = false;
    evidence.value = null;
    error.value = "";
    if (!selection) return;
    loading.value = true;
    try {
      const result = await api.evidence(
        selection.runId,
        selection.metric,
        selection.month,
      );
      if (sequence === requestSequence) evidence.value = result;
    } catch (e) {
      if (sequence === requestSequence)
        error.value = e instanceof Error ? e.message : String(e);
    } finally {
      if (sequence === requestSequence) loading.value = false;
    }
  },
  { immediate: true },
);
function drill(runId: string) {
  if (!state.evidence) return;
  trail.value = [...trail.value, { ...state.evidence }];
  navigating = true;
  state.evidence = { ...state.evidence, runId };
}
function back() {
  const selection = trail.value[trail.value.length - 1];
  if (!selection) return;
  trail.value = trail.value.slice(0, -1);
  navigating = true;
  state.evidence = selection;
}
onBeforeUnmount(() => {
  ++requestSequence;
});
</script>
<template>
  <el-drawer
    v-model="open"
    title="来源追溯"
    size="min(960px, 88vw)"
  >
    <el-button
      v-if="trail.length"
      link
      type="primary"
      @click="back"
    >
      ← 返回汇总来源
    </el-button>
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      :closable="false"
    />
    <el-skeleton
      v-if="loading"
      :rows="8"
      animated
    />
    <template v-else-if="evidence">
      <p class="muted">
        运行 {{ evidence.run_id }} · {{ evidence.month || "全周期" }} · 指标
        {{ evidence.metric }}
      </p>
      <p class="muted">
        输入版本：{{ evidence.revision_ids.join("、") || "无可用输入版本" }}
      </p>
      <el-alert
        title="金额、规则与记录来自该次运行保存的结果，不会替换为项目最新数据。金额展示单位为万元。"
        type="info"
        :closable="false"
      />
      <template v-if="evidence.members.length">
        <h3>汇总成员与贡献</h3>
        <p class="muted">
          下表利润为成员运行的未来12个月累计利润；点击查看所选月份和指标的来源。
        </p>
        <el-table :data="evidence.members">
          <el-table-column
            prop="project_name"
            label="项目"
            min-width="150"
          />
          <el-table-column
            label="状态"
            width="120"
          >
            <template #default="{ row }">
              {{
                runLabels[row.status] ?? row.status
              }}
            </template>
          </el-table-column>
          <el-table-column
            label="12月利润（万元）"
            width="165"
          >
            <template #default="{ row }">
              {{
                formatMoney(row.profit)
              }}
            </template>
          </el-table-column>
          <el-table-column
            label="绑定依据"
            width="150"
          >
            <template #default="{ row }">
              <el-button
                link
                type="primary"
                @click="drill(row.run_id)"
              >
                查看项目来源
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </template>
      <h3>组成记录与规则</h3>
      <SourceTable
        v-if="evidence.sources.length"
        :sources="evidence.sources"
      />
      <el-empty
        v-else
        :description="
          evidence.members.length
            ? '从成员项目继续下钻查看原记录'
            : '该指标和月份暂无组成记录，请结合运行状态核对'
        "
        :image-size="65"
      />
      <RouterLink
        :to="'/runs/' + evidence.run_id"
        @click="open = false"
      >
        查看运行快照与步骤 →
      </RouterLink>
    </template>
  </el-drawer>
</template>
<style scoped>
.muted {
  font-size: 12px;
  line-height: 1.7;
  overflow-wrap: anywhere;
}
h3 {
  margin-top: 24px;
  font-size: 16px;
}
</style>
