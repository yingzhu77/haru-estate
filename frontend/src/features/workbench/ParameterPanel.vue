<script setup lang="ts">
import { computed } from "vue";
import {
  DataAnalysis,
  Setting,
  RefreshLeft,
  Calendar,
} from "@element-plus/icons-vue";
import type { Revision, RunCreate } from "../../api/types";
import { state } from "../../state";
import { defaultOverrides, scenarioLabels } from "./useWorkbench";

const props = defineProps<{
  revision?: Revision;
  scenario: RunCreate["scenario"];
  loading: boolean;
  busy: boolean;
  disabled: boolean;
  selectedCount: number;
}>();
const emit = defineEmits<{
  "update:scenario": [value: RunCreate["scenario"]];
  changed: [];
  generate: [];
}>();
const overrides = computed(
  () => state.overrides[state.selectedProjectId] ?? defaultOverrides(),
);
const pricePercent = computed({
  get: () => Number(overrides.value.price_change) * 100,
  set: (value: number) => update({ price_change: (value / 100).toFixed(4) }),
});
const costPercent = computed({
  get: () => Number(overrides.value.remaining_cost_change) * 100,
  set: (value: number) =>
    update({ remaining_cost_change: (value / 100).toFixed(4) }),
});
const collectionDelay = computed({
  get: () => overrides.value.collection_delay,
  set: (value: number) => update({ collection_delay: value }),
});
function update(change: Partial<typeof overrides.value>) {
  state.overrides[state.selectedProjectId] = { ...overrides.value, ...change };
  emit("changed");
}
function updateDelivery(phaseId: string, value: number | undefined) {
  update({
    delivery_delays: {
      ...overrides.value.delivery_delays,
      [phaseId]: value ?? 0,
    },
  });
}
function reset() {
  state.overrides[state.selectedProjectId] = defaultOverrides();
  emit("changed");
}
const phases = computed(() => props.revision?.data.phases ?? []);
</script>

<template>
  <aside
    class="panel parameter-panel"
    aria-label="预测参数与情景"
  >
    <div class="panel-heading">
      <h2>参数与情景</h2>
      <el-icon class="muted">
        <Setting />
      </el-icon>
    </div>
    <div
      class="scenario-control"
      role="group"
      aria-label="预测情景"
    >
      <button
        v-for="(label, key) in scenarioLabels"
        :key="key"
        :class="{ active: scenario === key }"
        :aria-pressed="scenario === key"
        @click="emit('update:scenario', key)"
      >
        {{ label }}
      </button>
    </div>
    <template v-if="state.mode === 'project'">
      <div class="input-caption">
        <span>当前输入 <b v-if="revision">v{{ revision.version }}</b></span>
        <span v-if="revision">已结账至 {{ revision.data.actual_closed_through }}</span>
      </div>
      <el-skeleton
        v-if="loading"
        :rows="5"
        animated
      />
      <template v-else-if="revision">
        <div
          v-if="!phases.length"
          class="empty-input"
        >
          尚无分期计划。请先在数据管理中补充项目输入。
        </div>
        <div
          v-for="phase in phases"
          :key="phase.id"
          class="phase-summary"
        >
          <div class="phase-label">
            <span>{{ phase.name }}</span><el-icon><Calendar /></el-icon>
          </div>
          <dl>
            <div>
              <dt>计划售价</dt>
              <dd>
                {{ Number(phase.price).toLocaleString("zh-CN") }}
                <small>元/㎡</small>
              </dd>
            </div>
            <div>
              <dt>交付月份</dt>
              <dd>{{ phase.delivery_month }}</dd>
            </div>
          </dl>
        </div>
        <div class="section-heading">
          <h3>未来计划调整</h3>
          <button
            class="icon-reset"
            aria-label="重置当前项目情景调整"
            title="重置情景调整"
            @click="reset"
          >
            <el-icon><RefreshLeft /></el-icon>
          </button>
        </div>
        <div class="parameter-field">
          <label for="price-change">未售价格变化
            <b>{{ pricePercent > 0 ? "+" : "" }}{{ pricePercent }}%</b></label>
          <el-slider
            id="price-change"
            v-model="pricePercent"
            :min="-30"
            :max="30"
            :step="1"
            aria-label="未售价格变化百分比"
          />
        </div>
        <div class="parameter-field">
          <label for="cost-change">剩余成本变化
            <b>{{ costPercent > 0 ? "+" : "" }}{{ costPercent }}%</b></label>
          <el-slider
            id="cost-change"
            v-model="costPercent"
            :min="-30"
            :max="30"
            :step="1"
            aria-label="剩余成本变化百分比"
          />
        </div>
        <div class="delay-row">
          <label for="collection-delay">回款额外滞后</label><el-input-number
            id="collection-delay"
            v-model="collectionDelay"
            :min="0"
            :max="24"
            :precision="0"
            controls-position="right"
            aria-label="回款额外滞后月数"
          /><span>月</span>
        </div>
        <div
          v-for="phase in phases"
          :key="phase.id"
          class="delay-row"
        >
          <label :for="`delivery-${phase.id}`">{{ phase.name }}延期</label>
          <el-input-number
            :id="`delivery-${phase.id}`"
            :model-value="overrides.delivery_delays?.[phase.id] ?? 0"
            :min="0"
            :max="36"
            :precision="0"
            controls-position="right"
            :aria-label="`${phase.name}交付延期月数`"
            @update:model-value="updateDelivery(phase.id, $event)"
          /><span>月</span>
        </div>
        <p class="field-note">
          仅调整未来计划，已签合同与历史实际保持原值。其他输入可在数据管理中修订。
        </p>
      </template>
    </template>
    <template v-else>
      <div class="portfolio-note">
        <span class="scope-count">{{ selectedCount }}</span><span>个项目纳入本次汇总</span>
      </div>
      <p class="field-note">
        采用共同预测时点和同一情景，绑定本次各项目的输入快照。
      </p>
      <el-checkbox-group
        v-model="state.selectedProjectIds"
        class="project-checks"
      >
        <el-checkbox
          v-for="project in state.projects.filter((item) => !item.archived)"
          :key="project.id"
          :value="project.id"
        >
          {{ project.name }}
        </el-checkbox>
      </el-checkbox-group>
      <div class="boundary-note">
        <b>独立核算，按月汇总</b>
        <p>
          项目现金不默认互相调拨。资金缺口保留各项目风险，不能用另一项目盈余自动抵销。
        </p>
      </div>
      <p class="field-note">
        需要调整售价或成本时，切至对应单项目编辑；本次汇总使用各项目现有情景草稿。
      </p>
    </template>
    <div class="panel-footer">
      <el-button
        type="primary"
        :icon="DataAnalysis"
        :loading="busy"
        :disabled="disabled || loading"
        class="generate-button"
        @click="emit('generate')"
      >
        {{
          state.mode === "portfolio" ? "生成项目汇总" : "生成情景预测"
        }}
      </el-button>
      <RouterLink
        to="/data"
        class="secondary-action"
      >
        <el-icon><Setting /></el-icon>管理数据与假设
      </RouterLink>
      <p class="draft-caption">
        情景草稿提交后随预测运行保存
      </p>
    </div>
  </aside>
</template>

<style scoped>
.parameter-panel {
  padding: 18px 17px;
  display: flex;
  flex-direction: column;
}
.panel-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 18px;
}
.panel-heading h2 {
  margin: 0;
  font-size: 17px;
}
.scenario-control {
  display: flex;
  padding: 3px;
  background: var(--soft);
  border: 1px solid var(--border);
  border-radius: 7px;
}
.scenario-control button {
  flex: 1;
  color: inherit;
  border: 0;
  background: transparent;
  border-radius: 5px;
  padding: 9px 0;
  font-size: 13px;
}
.scenario-control button.active {
  color: #fff;
  background: var(--accent);
  box-shadow: 0 2px 5px #203b6315;
}
.input-caption {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 10px;
  color: var(--muted);
  margin: 18px 0 11px;
}
.input-caption b {
  color: var(--accent);
}
.phase-summary {
  padding: 11px 0;
  border-bottom: 1px solid var(--border);
}
.phase-label {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 600;
}
.phase-label .el-icon {
  color: var(--muted);
}
dl {
  margin: 9px 0 0;
}
dl div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 7px;
  font-size: 12px;
}
dt {
  color: var(--muted);
}
dd {
  margin: 0;
  font-variant-numeric: tabular-nums;
}
dd small {
  font-size: 10px;
  color: var(--muted);
}
.section-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 18px 0 14px;
}
.section-heading h3 {
  font-size: 14px;
  margin: 0;
}
.icon-reset {
  border: 0;
  background: none;
  color: var(--muted);
  padding: 4px;
  display: flex;
}
.parameter-field {
  margin-bottom: 13px;
}
.parameter-field label {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
}
.parameter-field b {
  color: var(--accent);
  font-variant-numeric: tabular-nums;
}
.parameter-field :deep(.el-slider) {
  height: 25px;
  padding: 0 4px;
}
.parameter-field :deep(.el-slider__button) {
  width: 14px;
  height: 14px;
}
.delay-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 11px 0;
  font-size: 11px;
}
.delay-row label {
  flex: 1;
  overflow-wrap: anywhere;
}
.delay-row :deep(.el-input-number) {
  width: 82px;
}
.delay-row :deep(.el-input__inner) {
  font-size: 12px;
}
.field-note {
  font-size: 11px;
  line-height: 1.75;
  color: var(--muted);
  margin: 13px 0;
}
.panel-footer {
  margin-top: auto;
  padding-top: 17px;
}
.generate-button {
  width: 100%;
  height: 41px;
  font-size: 13px;
  font-weight: 600;
}
.secondary-action {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  border: 1px solid var(--border);
  border-radius: 7px;
  padding: 11px 0;
  margin-top: 10px;
  font-size: 12px;
  background: var(--soft);
}
.draft-caption {
  text-align: center;
  color: var(--muted);
  font-size: 10px;
  margin: 10px 0 0;
}
.portfolio-note {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-top: 26px;
  font-size: 12px;
  color: var(--muted);
}
.scope-count {
  font-size: 32px;
  color: var(--accent);
  font-weight: 700;
}
.project-checks {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 12px 0 22px;
}
.project-checks :deep(.el-checkbox__label) {
  white-space: normal;
  font-size: 13px;
}
.boundary-note {
  padding: 14px;
  border-radius: 7px;
  background: var(--soft);
  font-size: 12px;
  line-height: 1.7;
}
.boundary-note p {
  margin: 8px 0 0;
  color: var(--muted);
}
.empty-input {
  font-size: 12px;
  color: var(--muted);
  padding: 20px 0;
  line-height: 1.8;
}
</style>
