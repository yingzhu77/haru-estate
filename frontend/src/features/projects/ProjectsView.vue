<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus/es/components/message/index'
import { ElMessageBox } from 'element-plus/es/components/message-box/index'
import { api } from '../../api/client'
import type { Project } from '../../api/types'
import { refreshProjects, state } from '../../state'

const router = useRouter()
const name = ref('')
const template = ref<'blank' | 'demo'>('blank')
const busy = ref(false)
const error = ref('')
const showArchived = ref(false)
const projects = computed(() => state.projects.filter((p) => showArchived.value || !p.archived))
async function create() {
  if (busy.value) return
  if (!name.value.trim()) {
    error.value = '请填写项目名称'
    return
  }
  busy.value = true
  error.value = ''
  try {
    const project = await api.createProject({
      name: name.value.trim(),
      template: template.value,
    })
    await refreshProjects()
    state.selectedProjectId = project.id
    name.value = ''
    ElMessage.success('项目已创建，请完善分期与数据')
    await router.push('/data')
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    busy.value = false
  }
}
async function rename(project: Project) {
  try {
    const result = await ElMessageBox.prompt('修改名称不改变项目编号或历史运行。', '编辑项目名称', {
      inputValue: project.name,
      inputValidator: (v) => !!v?.trim() || '名称不能为空',
    })
    await update(project, result.value.trim(), project.archived)
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') error.value = e instanceof Error ? e.message : String(e)
  }
}
async function archive(project: Project) {
  try {
    await ElMessageBox.confirm(
      project.archived
        ? '恢复后可以继续编辑和预测。'
        : '归档后从工作台隐藏，历史版本和汇总成员仍然保留。',
      project.archived ? '恢复项目' : '归档项目',
    )
    await update(project, project.name, !project.archived)
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') error.value = e instanceof Error ? e.message : String(e)
  }
}
async function update(project: Project, nextName: string, archived: boolean) {
  busy.value = true
  error.value = ''
  try {
    await api.patchProject(project.id, {
      name: nextName,
      archived,
      base_version: project.version,
    })
    await refreshProjects()
    if (state.projects.find((p) => p.id === state.selectedProjectId)?.archived)
      state.selectedProjectId = state.projects.find((p) => !p.archived)?.id ?? ''
    state.selectedProjectIds = state.selectedProjectIds.filter((id) =>
      state.projects.some((p) => p.id === id && !p.archived),
    )
  } finally {
    busy.value = false
  }
}
function edit(project: Project) {
  state.selectedProjectId = project.id
  void router.push('/data')
}
</script>

<template>
  <div class="page-heading">
    <div>
      <h1>项目管理</h1>
      <p class="muted">
        每个项目独立保存输入与预测，汇总始终绑定当次项目版本。
      </p>
    </div>
    <el-switch
      v-model="showArchived"
      active-text="显示已归档"
    />
  </div>
  <el-alert
    v-if="error"
    :title="error"
    type="error"
    show-icon
    :closable="false"
  />
  <section class="panel create-panel">
    <h2>新建住宅项目</h2>
    <div class="toolbar">
      <el-input
        v-model="name"
        aria-label="新项目名称"
        maxlength="100"
        placeholder="项目名称"
        class="name-field"
        @keyup.enter="create"
      />
      <el-radio-group v-model="template">
        <el-radio-button value="blank">
          空白项目
        </el-radio-button><el-radio-button value="demo">
          模拟模板
        </el-radio-button>
      </el-radio-group>
      <el-button
        type="primary"
        :loading="busy"
        @click="create"
      >
        创建项目
      </el-button>
    </div>
    <p class="muted">
      {{
        template === 'blank'
          ? '空白项目没有业务记录，需补齐分期、成本与计划后才能预测。'
          : '模板内全部经营数据均为模拟演示，将创建独立副本，不复制其他项目的预测历史。'
      }}
    </p>
  </section>
  <section class="panel">
    <h2>住宅项目 · {{ projects.length }}</h2>
    <el-table
      :data="projects"
      row-key="id"
    >
      <el-table-column
        prop="name"
        label="项目名称"
        min-width="190"
      />
      <el-table-column
        label="状态"
        width="110"
      >
        <template #default="{ row }">
          <el-tag :type="row.archived ? 'info' : 'success'">
            {{ row.archived ? '已归档' : '进行中' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column
        label="当前版本"
        width="110"
      >
        <template #default="{ row }">
          v{{ row.version }}
        </template>
      </el-table-column>
      <el-table-column
        prop="id"
        label="项目编号"
        min-width="190"
      />
      <el-table-column
        label="操作"
        width="300"
      >
        <template #default="{ row }">
          <el-button
            link
            type="primary"
            :disabled="row.archived || busy"
            @click="edit(row)"
          >
            分期与数据
          </el-button><el-button
            link
            :disabled="busy"
            @click="rename(row)"
          >
            改名
          </el-button><el-button
            link
            :disabled="busy"
            @click="archive(row)"
          >
            {{ row.archived ? '恢复' : '归档' }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </section>
</template>

<style scoped>
.create-panel {
  margin-bottom: 18px;
}
.name-field {
  width: 300px;
}
.create-panel p {
  font-size: 13px;
  margin-bottom: 0;
}
</style>
