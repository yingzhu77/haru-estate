<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { onBeforeRouteLeave } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { api } from "../../api/client";
import type { Dataset, ImportPreview, Revision } from "../../api/types";
import { refreshProjects, state, formatMoney } from "../../state";
import DatasetEditor from "./DatasetEditor.vue";
import { cloneData, draftBases, isDirty, metricLabels } from "./editor";

const error = ref("");
const busy = ref(false);
const loading = ref(false);
const base = ref<Revision | null>(null);
const knownOn = ref(state.informationCutoff);
const note = ref("手动修订");
const preview = ref<ImportPreview | null>(null);
const project = computed(() =>
  state.projects.find((p) => p.id === state.selectedProjectId),
);
const draft = computed<Dataset | undefined>({
  get: () => state.drafts[state.selectedProjectId],
  set: (value) => {
    if (value) state.drafts[state.selectedProjectId] = value;
  },
});
const dirty = computed(() => isDirty(draft.value, base.value ?? undefined));
let loadSequence = 0;
function accept(revision: Revision, submitted?: Dataset) {
  draftBases[revision.project_id] = revision;
  // A late response must not discard edits made while the request was in flight.
  const current = state.drafts[revision.project_id];
  if (
    !submitted ||
    !current ||
    JSON.stringify(current) === JSON.stringify(submitted)
  ) {
    state.drafts[revision.project_id] = cloneData(revision.data);
  }
  if (state.selectedProjectId === revision.project_id) {
    base.value = revision;
    preview.value = null;
  }
}
async function load(id: string) {
  const sequence = ++loadSequence;
  base.value = null;
  preview.value = null;
  error.value = "";
  if (!id) {
    loading.value = false;
    return;
  }
  loading.value = true;
  try {
    if (state.drafts[id] && draftBases[id]) {
      base.value = draftBases[id];
      return;
    }
    const revision = await api.input(id);
    if (sequence !== loadSequence) return;
    accept(revision);
  } catch (e) {
    if (sequence === loadSequence)
      error.value = e instanceof Error ? e.message : String(e);
  } finally {
    if (sequence === loadSequence) loading.value = false;
  }
}
watch(
  () => state.selectedProjectId,
  (id, oldId) => {
    if (oldId && isDirty(state.drafts[oldId], draftBases[oldId]))
      ElMessage.info(
        "上一项目的未保存草稿已保留在当前会话，关闭页面前请保存。",
      );
    void load(id);
  },
  { immediate: true },
);
async function save() {
  if (
    busy.value ||
    !draft.value ||
    !base.value ||
    base.value.project_id !== state.selectedProjectId
  )
    return;
  busy.value = true;
  error.value = "";
  const id = base.value.project_id;
  const submitted = cloneData(draft.value);
  try {
    const revision = await api.revise(id, {
      base_version: base.value.version,
      known_on: knownOn.value,
      note: note.value,
      data: submitted,
    });
    accept(revision, submitted);
    await refreshProjects();
    ElMessage.success("项目已保存新版本，历史预测保持原快照。");
  } catch (e) {
    const message =
      (e instanceof Error ? e.message : String(e)) +
      "；草稿已保留，请核对版本后重试。";
    if (state.selectedProjectId === id) error.value = message;
    else ElMessage.error("此前项目保存失败：" + message);
  } finally {
    busy.value = false;
  }
}
async function reload() {
  if (busy.value) return;
  const id = state.selectedProjectId;
  try {
    if (dirty.value)
      await ElMessageBox.confirm(
        "重新载入会放弃该项目的未保存草稿，其他项目草稿不变。",
        "重新载入已保存版本",
      );
    if (state.selectedProjectId !== id) return;
    busy.value = true;
    const revision = await api.input(id);
    accept(revision);
    if (state.selectedProjectId === id) error.value = "";
  } catch (e) {
    if (e !== "cancel" && e !== "close")
      error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}
async function upload(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file || busy.value) return;
  if (dirty.value) {
    error.value = "请先保存或放弃当前草稿，再预览导入，避免覆盖草稿。";
    return;
  }
  busy.value = true;
  error.value = "";
  preview.value = null;
  const id = state.selectedProjectId;
  try {
    const result = await api.previewImport(id, file);
    if (id === state.selectedProjectId) preview.value = result;
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}
async function confirmImport() {
  const result = preview.value;
  if (
    busy.value ||
    dirty.value ||
    !result ||
    result.errors.length ||
    !result.additions.length ||
    result.project_id !== state.selectedProjectId
  )
    return;
  busy.value = true;
  error.value = "";
  const submitted = draft.value ? cloneData(draft.value) : undefined;
  try {
    const revision = await api.confirmImport(result.project_id, {
      base_version: result.base_version,
      known_on: knownOn.value,
      records: result.additions,
    });
    accept(revision, submitted);
    await refreshProjects();
    ElMessage.success("增量记录已保存为新版本。");
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    busy.value = false;
  }
}
function downloadTemplate() {
  const blob = new Blob(
    ["\uFEFFid,phase_id,month,known_on,metric,amount,note,contract_id\r\n"],
    { type: "text/csv;charset=utf-8" },
  );
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "actuals-template.csv";
  link.click();
  URL.revokeObjectURL(url);
}
function beforeUnload(event: BeforeUnloadEvent) {
  if (
    Object.entries(state.drafts).some(([id, value]) =>
      isDirty(value, draftBases[id]),
    )
  ) {
    event.preventDefault();
    event.returnValue = "";
  }
}
window.addEventListener("beforeunload", beforeUnload);
onBeforeUnmount(() => {
  ++loadSequence;
  window.removeEventListener("beforeunload", beforeUnload);
});
onBeforeRouteLeave(async () => {
  if (!dirty.value) return true;
  try {
    await ElMessageBox.confirm(
      "草稿会暂存于当前页面会话，刷新或关闭页面会丢失。仍要离开吗？",
      "有未保存修改",
    );
    return true;
  } catch {
    return false;
  }
});
</script>
<template>
  <div class="page-heading">
    <div>
      <h1>数据与假设</h1>
      <p class="muted">
        {{ project?.name ?? "请先选择项目" }} · 历史实际与未来计划分别维护
      </p>
    </div>
    <el-tag
      v-if="base"
      :type="dirty ? 'warning' : 'success'"
    >
      {{ dirty ? "有未保存草稿" : "已保存" }} · v{{ base.version }}
    </el-tag>
  </div>
  <el-alert
    v-if="error"
    :title="error"
    type="error"
    :closable="false"
    show-icon
  />
  <el-empty
    v-if="!state.selectedProjectId"
    description="还没有可编辑项目"
  >
    <RouterLink to="/projects">
      创建项目
    </RouterLink>
  </el-empty>
  <el-skeleton
    v-else-if="loading"
    :rows="8"
    animated
  />
  <template v-else-if="draft && base">
    <section class="panel revision-panel">
      <div class="toolbar">
        <label>本次信息获知日
          <input
            v-model="knownOn"
            type="date"
            aria-label="修订信息获知日"
          ></label><label>已结账至
          <input
            v-model="draft.actual_closed_through"
            type="month"
            aria-label="已结账月份"
          ></label><el-input
          v-model="note"
          placeholder="修订说明"
          aria-label="修订说明"
          maxlength="300"
          style="max-width: 320px"
        /><el-button
          type="primary"
          :loading="busy"
          :disabled="project?.archived"
          @click="save"
        >
          保存为新版本
        </el-button><el-button
          :disabled="busy"
          @click="reload"
        >
          重新载入
        </el-button>
      </div>
      <p class="muted">
        输入版本 {{ base.id }} ·
        {{
          base.note
        }}。保存不会自动重算；预测只能使用信息截止日当时已知的版本。
      </p>
      <el-alert
        v-if="!draft.phases?.length"
        title="尚无分期，请补齐分期与成本计划。当前项目不具备预测条件。"
        type="warning"
        :closable="false"
      />
    </section>
    <section class="panel">
      <fieldset :disabled="busy || project?.archived">
        <DatasetEditor
          v-model="draft"
          :known-on="knownOn"
        />
      </fieldset>
    </section>
    <section class="panel import-panel">
      <h2>增量导入历史实际</h2>
      <p class="muted">
        CSV 必填字段：id、phase_id、month、known_on、metric、amount；选填
        note、contract_id。金额为元，分期编号必须属于当前项目，历史回款可关联合同。上传资料仅作为数据读取。
      </p>
      <div class="toolbar">
        <el-button @click="downloadTemplate">
          下载空白 CSV 模板
        </el-button><label class="file-label">选择 CSV
          <input
            type="file"
            accept=".csv,text/csv"
            :disabled="busy || dirty || project?.archived"
            aria-label="导入实际记录CSV"
            @change="upload"
          ></label>
      </div>
      <details class="muted">
        <summary>查看指标字段取值</summary>
        <p>
          {{
            Object.entries(metricLabels)
              .map(([key, label]) => key + "：" + label)
              .join("；")
          }}
        </p>
      </details>
      <div
        v-if="preview"
        class="preview"
      >
        <div class="toolbar">
          <el-tag>新增 {{ preview.additions.length }} 条</el-tag><el-tag type="info">
            重复 {{ preview.duplicates.length }} 条
          </el-tag><el-tag :type="preview.errors.length ? 'danger' : 'success'">
            错误 {{ preview.errors.length }} 条
          </el-tag>
        </div>
        <ul
          v-if="preview.errors.length"
          class="error"
        >
          <li
            v-for="message in preview.errors"
            :key="message"
          >
            {{ message }}
          </li>
        </ul>
        <p
          v-if="preview.duplicates.length"
          class="muted"
        >
          重复编号：{{ preview.duplicates.join("、") }}
        </p>
        <el-table :data="preview.additions">
          <el-table-column
            prop="id"
            label="记录编号"
          /><el-table-column
            prop="phase_id"
            label="分期编号"
          /><el-table-column
            prop="month"
            label="月份"
          /><el-table-column
            label="指标"
          >
            <template #default="{ row }">
              {{
                metricLabels[row.metric as keyof typeof metricLabels]
              }}
            </template>
          </el-table-column><el-table-column label="金额（万元）">
            <template #default="{ row }">
              {{
                formatMoney(row.amount)
              }}
            </template>
          </el-table-column>
        </el-table>
        <el-button
          type="primary"
          :disabled="
            dirty || !!preview.errors.length || !preview.additions.length
          "
          :loading="busy"
          @click="confirmImport"
        >
          确认导入并生成新版本
        </el-button>
      </div>
    </section>
  </template>
</template>
<style scoped>
.revision-panel,
.import-panel {
  margin: 18px 0;
}
.revision-panel .muted,
.import-panel .muted {
  font-size: 12px;
  line-height: 1.7;
}
.toolbar label {
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.toolbar input[type="date"],
.toolbar input[type="month"] {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 7px;
  color: inherit;
  background: var(--solid);
}
fieldset {
  border: 0;
  padding: 0;
  margin: 0;
  min-width: 0;
}
.file-label {
  padding: 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
}
.preview {
  margin-top: 20px;
}
.preview > .el-button {
  margin-top: 16px;
}
</style>
