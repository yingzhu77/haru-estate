<script setup lang="ts">
import { onMounted } from 'vue'
import { Sunny, Moon, ArrowRight } from '@element-plus/icons-vue'
import { state, setTheme, refreshProjects } from './state'
import EvidenceDrawer from './features/evidence/EvidenceDrawer.vue'
setTheme(state.theme)
onMounted(() =>
  refreshProjects().catch((e: Error) => {
    state.error = e.message
  }),
)
</script>
<template>
  <div class="app-shell">
    <header class="topbar">
      <RouterLink
        class="brand"
        to="/"
      >
        <img
          src="/brand/logo.png"
          alt="晴屿 Logo"
        ><span>晴屿 <b>HaruEstate</b><small>地产预算与利润预测</small></span>
      </RouterLink>
      <nav aria-label="主导航">
        <RouterLink to="/">
          预测工作台
        </RouterLink><RouterLink to="/data">
          数据管理
        </RouterLink><RouterLink to="/runs">
          历史预测
        </RouterLink>
      </nav>
      <div class="header-actions">
        <span class="demo-badge">模拟演示 · 非真实经营数据</span>
        <div
          class="theme-switch"
          aria-label="主题切换"
        >
          <button
            :class="{ selected: state.theme === 'acg' }"
            @click="setTheme('acg')"
          >
            <el-icon><Sunny /></el-icon>晴日
          </button><button
            :class="{ selected: state.theme === 'minimal' }"
            @click="setTheme('minimal')"
          >
            <el-icon><Moon /></el-icon>简约
          </button>
        </div>
      </div>
    </header>
    <div class="contextbar">
      <el-select
        v-model="state.selectedProjectId"
        aria-label="当前项目"
        style="width: 230px"
      >
        <el-option
          v-for="p in state.projects.filter((p) => !p.archived)"
          :key="p.id"
          :label="p.name + ' · 模拟项目'"
          :value="p.id"
        />
      </el-select>
      <RouterLink
        to="/projects"
        class="quiet-link"
      >
        管理项目 <el-icon><ArrowRight /></el-icon>
      </RouterLink>
      <label>预测基准日
        <input
          v-model="state.forecastOrigin"
          type="date"
          aria-label="预测基准日"
        ></label>
      <label>信息截止
        <input
          v-model="state.informationCutoff"
          type="date"
          aria-label="信息截止"
        ></label>
      <span class="muted context-note">模拟管理口径 · 人民币 · 金额可追溯</span>
    </div>
    <el-alert
      v-if="state.error"
      :title="state.error"
      type="error"
      show-icon
      @close="state.error = ''"
    />
    <main><RouterView /></main>
    <EvidenceDrawer />
  </div>
</template>
