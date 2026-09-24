import { reactive } from 'vue'
import { api } from './api/client'
import type { Dataset, Project, Run, Overrides } from './api/types'
export const state = reactive({
  theme: (localStorage.getItem('haru-theme') === 'minimal' ? 'minimal' : 'acg') as
    'minimal' | 'acg',
  projects: [] as Project[],
  selectedProjectId: '',
  selectedProjectIds: [] as string[],
  mode: 'project' as 'project' | 'portfolio',
  forecastOrigin: '2026-08-31',
  informationCutoff: '2026-08-31',
  activeRun: null as Run | null,
  drafts: {} as Record<string, Dataset>,
  overrides: {} as Record<string, Overrides>,
  error: '',
  evidence: null as { runId: string; metric: string; month?: string; months?: string[] } | null,
})
export async function refreshProjects() {
  state.projects = await api.projects()
  if (!state.selectedProjectId)
    state.selectedProjectId = state.projects.find((p) => !p.archived)?.id ?? ''
  if (!state.selectedProjectIds.length)
    state.selectedProjectIds = state.projects.filter((p) => !p.archived).map((p) => p.id)
}
export function setTheme(theme: 'minimal' | 'acg') {
  state.theme = theme
  localStorage.setItem('haru-theme', theme)
  document.documentElement.dataset.theme = theme
}
export function showEvidence(runId: string, metric = 'profit', month?: string, months?: string[]) {
  state.evidence = { runId, metric, month, months }
}
export const formatMoney = (value: string | null | undefined) =>
  value == null
    ? '—'
    : (Number(value) / 10000).toLocaleString('zh-CN', { maximumFractionDigits: 2 })
