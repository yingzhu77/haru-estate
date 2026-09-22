<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { api } from "../../api/client";
import type { Revision, Run } from "../../api/types";
import { formatMoney, showEvidence } from "../../state";
import { runLabels, scenarioLabels } from "../data/editor";
const route = useRoute();
const run = ref<Run | null>(null);
const snapshots = ref<Revision[]>([]);
const loading = ref(false);
const resuming = ref(false);
const error = ref("");
const snapshotError = ref("");
let sequence = 0;
let timer: ReturnType<typeof setTimeout> | undefined;
const recoverable = computed(
  () =>
    !!run.value &&
    ["interrupted", "failed", "incomplete"].includes(run.value.status),
);
async function load(id: string, withSnapshots = false) {
  const request = ++sequence;
  if (timer) clearTimeout(timer);
  loading.value = withSnapshots;
  error.value = "";
  try {
    const result = await api.run(id);
    if (request !== sequence) return;
    run.value = result;
    if (withSnapshots) {
      const pairs = result.members?.length
        ? result.members.map((member) => ({
            projectId: member.project_id,
            revisionId: member.revision_id,
          }))
        : result.project_ids.map((projectId, index) => ({
            projectId,
            revisionId: result.revision_ids[index],
          }));
      const values = await Promise.allSettled(
        pairs
          .filter((pair) => pair.revisionId)
          .map((pair) => api.input(pair.projectId, pair.revisionId)),
      );
      if (request !== sequence) return;
      snapshots.value = values.flatMap((value) =>
        value.status === "fulfilled" ? [value.value] : [],
      );
      snapshotError.value = values.some((value) => value.status === "rejected")
        ? "部分输入快照读取失败。未使用最新输入替代，请刷新重试。"
        : "";
    }
    if (["queued", "running", "waiting"].includes(result.status))
      timer = setTimeout(() => {
        void load(id);
      }, 1500);
  } catch (e) {
    if (request === sequence)
      error.value = e instanceof Error ? e.message : String(e);
  } finally {
    if (request === sequence) loading.value = false;
  }
}
async function resume() {
  if (!run.value || resuming.value) return;
  resuming.value = true;
  error.value = "";
  const id = run.value.id;
  try {
    await api.resume(id);
    if (String(route.params.id) === id) await load(id);
  } catch (e) {
    if (String(route.params.id) === id)
      error.value = e instanceof Error ? e.message : String(e);
  } finally {
    resuming.value = false;
  }
}
watch(
  () => String(route.params.id),
  (id) => {
    run.value = null;
    snapshots.value = [];
    snapshotError.value = "";
    void load(id, true);
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  ++sequence;
  if (timer) clearTimeout(timer);
});
</script>
<template>
  <div class="page-heading">
    <div>
      <RouterLink to="/runs">
        ← 返回历史预测
      </RouterLink>
      <h1>运行详情</h1>
    </div>
    <el-button
      :loading="loading"
      @click="load(String(route.params.id), true)"
    >
      刷新
    </el-button>
  </div>
  <el-alert
    v-if="error"
    :title="error"
    type="error"
    :closable="false"
  />
  <el-skeleton
    v-if="loading && !run"
    :rows="10"
    animated
  />
  <template v-if="run">
    <section class="panel">
      <div class="page-heading">
        <h2>
          {{ run.project_names.join("、") }} ·
          {{ run.kind === "portfolio" ? "项目汇总" : "单项目预测" }}
        </h2>
        <el-tag
          :type="run.result ? 'success' : run.error ? 'danger' : 'info'"
        >
          {{ runLabels[run.status] ?? run.status }}
        </el-tag>
      </div>
      <el-descriptions
        :column="3"
        border
      >
        <el-descriptions-item label="运行编号">
          {{
            run.id
          }}
        </el-descriptions-item>
        <el-descriptions-item label="预测基准">
          {{
            run.forecast_origin
          }}
        </el-descriptions-item>
        <el-descriptions-item label="信息截止">
          {{
            run.information_cutoff
          }}
        </el-descriptions-item>
        <el-descriptions-item label="创建时间">
          {{
            run.created_at
          }}
        </el-descriptions-item>
        <el-descriptions-item label="情景">
          {{
            scenarioLabels[run.scenario]
          }}
        </el-descriptions-item>
        <el-descriptions-item label="尝试次数">
          {{
            run.attempt
          }}
        </el-descriptions-item>
      </el-descriptions>
      <p v-if="run.parent_id">
        <RouterLink :to="'/runs/' + run.parent_id">
          查看所属汇总 / 关联运行 →
        </RouterLink>
      </p>
      <el-alert
        v-if="run.error"
        :title="run.error"
        type="error"
        :closable="false"
        show-icon
        class="spaced"
      />
      <div
        v-if="recoverable"
        class="toolbar spaced"
      >
        <el-button
          type="primary"
          :loading="resuming"
          @click="resume"
        >
          使用原输入恢复 / 重试
        </el-button><span class="muted">修正了输入时应创建新预测，本操作不会换用最新版本。</span>
      </div>
    </section>
    <section
      v-if="run.members?.length"
      class="panel"
    >
      <h2>当次汇总成员</h2>
      <p class="muted">
        此处绑定成员运行与修订编号；归档、新增项目或后续重算不会改变本次汇总。
      </p>
      <el-table :data="run.members">
        <el-table-column
          prop="project_name"
          label="项目"
        /><el-table-column
          label="状态"
        >
          <template #default="{ row }">
            {{
              runLabels[row.status] ?? row.status
            }}
          </template>
        </el-table-column><el-table-column
          prop="revision_id"
          label="绑定输入版本"
          min-width="230"
        /><el-table-column label="12月利润（万元）">
          <template #default="{ row }">
            {{
              formatMoney(row.profit)
            }}
          </template>
        </el-table-column><el-table-column
          prop="error"
          label="缺项 / 错误"
        /><el-table-column
          label="下钻"
        >
          <template #default="{ row }">
            <RouterLink :to="'/runs/' + row.run_id">
              绑定子运行 →
            </RouterLink>
          </template>
        </el-table-column>
      </el-table>
    </section>
    <section class="panel">
      <h2>程序执行记录</h2>
      <el-empty
        v-if="!run.steps?.length"
        description="任务已创建，等待执行步骤"
        :image-size="50"
      />
      <el-timeline v-else>
        <el-timeline-item
          v-for="step in run.steps"
          :key="step.sequence + '-' + step.attempt"
          :timestamp="step.created_at"
          placement="top"
        >
          <strong>{{ step.name }} ·
            {{ runLabels[step.status] ?? step.status }}</strong>
          <p>{{ step.message }}</p>
          <small class="muted">步骤 {{ step.sequence }} · 尝试 {{ step.attempt }}</small>
        </el-timeline-item>
      </el-timeline>
    </section>
    <section
      v-if="run.result"
      class="panel"
    >
      <div class="page-heading">
        <h2>已保存计算结果</h2>
        <el-button
          link
          type="primary"
          @click="showEvidence(run.id)"
        >
          查看利润来源 →
        </el-button>
      </div>
      <p class="muted">
        {{ run.result.profit_basis }} · {{ run.result.currency }} ·
        展示单位：万元 · 规则 {{ run.result.rule_version }}
      </p>
      <div class="summary-grid">
        <div>
          <small>下月利润</small><strong>{{
            formatMoney(run.result.summary.next_month_profit)
          }}</strong>
        </div>
        <div>
          <small>未来12个月利润</small><strong>{{
            formatMoney(run.result.summary.twelve_month_profit)
          }}</strong>
        </div>
        <div>
          <small>全周期利润</small><strong>{{
            formatMoney(run.result.summary.lifecycle_profit)
          }}</strong>
        </div>
        <div>
          <small>最大未覆盖缺口</small><strong>{{
            formatMoney(run.result.summary.max_funding_gap)
          }}</strong>
        </div>
      </div>
      <el-alert
        v-for="warning in run.result.warnings"
        :key="warning"
        :title="warning"
        type="warning"
        :closable="false"
        class="spaced"
      />
      <el-table
        :data="run.result.months"
        max-height="450"
      >
        <el-table-column
          prop="month"
          label="月份"
          width="100"
        /><el-table-column label="确认收入">
          <template #default="{ row }">
            {{
              formatMoney(row.revenue)
            }}
          </template>
        </el-table-column><el-table-column label="结转成本">
          <template #default="{ row }">
            {{
              formatMoney(row.cogs)
            }}
          </template>
        </el-table-column><el-table-column label="利润">
          <template #default="{ row }">
            {{
              formatMoney(row.profit)
            }}
          </template>
        </el-table-column><el-table-column label="净现金流">
          <template #default="{ row }">
            {{
              formatMoney(row.net_cash_flow)
            }}
          </template>
        </el-table-column><el-table-column
          label="依据"
          width="90"
        >
          <template #default="{ row }">
            <el-button
              link
              type="primary"
              @click="showEvidence(run.id, 'profit', row.month)"
            >
              查看
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>
    <section class="panel">
      <h2>不可变输入快照</h2>
      <el-alert
        v-if="snapshotError"
        :title="snapshotError"
        type="error"
        :closable="false"
      />
      <p class="muted">
        下面是本次运行绑定的历史输入，可展开核对所有字段；编辑请前往数据管理创建新版本。
      </p>
      <details
        v-for="snapshot in snapshots"
        :key="snapshot.id"
      >
        <summary>
          项目 {{ snapshot.project_id }} · v{{ snapshot.version }} · 获知日
          {{ snapshot.known_on }} · {{ snapshot.note }}
        </summary>
        <p class="muted">
          版本编号 {{ snapshot.id }} · 已结账至
          {{ snapshot.data.actual_closed_through }}
        </p>
        <pre>{{ JSON.stringify(snapshot.data, null, 2) }}</pre>
      </details>
      <el-empty
        v-if="!snapshots.length && !loading"
        description="没有可读取的绑定输入，请结合运行错误核对"
        :image-size="50"
      />
    </section>
  </template>
</template>
<style scoped>
.page-heading h1 {
  margin-top: 8px;
}
.panel {
  margin-bottom: 18px;
}
.page-heading h2 {
  margin: 0;
}
.muted {
  font-size: 12px;
  line-height: 1.7;
}
.spaced {
  margin-top: 16px;
}
.summary-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 15px;
  margin: 20px 0;
}
.summary-grid > div {
  padding: 18px;
  background: var(--soft);
  border: 1px solid var(--border);
  border-radius: 8px;
}
.summary-grid strong {
  display: block;
  font-size: 24px;
  margin-top: 8px;
  font-variant-numeric: tabular-nums;
}
.summary-grid small {
  color: var(--muted);
}
details {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px;
  margin: 10px 0;
}
summary {
  cursor: pointer;
  font-size: 13px;
}
pre {
  background: var(--soft);
  padding: 16px;
  max-height: 400px;
  overflow: auto;
  line-height: 1.5;
  font-size: 12px;
}
</style>
