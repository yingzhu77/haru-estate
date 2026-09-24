import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { api } from '../../api/client'
import type { Overrides, Revision, Run, RunCreate } from '../../api/types'
import { state } from '../../state'

export const scenarioLabels = {
  base: '基准',
  optimistic: '乐观',
  prudent: '审慎',
}
export const statusLabels: Record<string, string> = {
  queued: '等待计算',
  waiting: '等待子项目',
  running: '计算中',
  completed: '已完成',
  failed: '失败',
  incomplete: '汇总未完成',
  interrupted: '中断待恢复',
}
export const isRunning = (run: Run | null) =>
  !!run && ['queued', 'waiting', 'running'].includes(run.status)
export const scopeKey = (kind: Run['kind'], ids: string[]) => `${kind}:${[...ids].sort().join(',')}`
export const matchesScope = (run: Run, kind: Run['kind'], ids: string[]) =>
  scopeKey(run.kind, run.project_ids) === scopeKey(kind, ids)
export const defaultOverrides = (): Overrides => ({
  price_change: '0',
  remaining_cost_change: '0',
  collection_delay: 0,
  delivery_delays: {},
})

// Route changes keep the editor's in-memory drafts. The server remains the source of truth for runs.
const editor = reactive({ scenario: 'base' as RunCreate['scenario'] })
const completedByScope = new Map<string, Run>()

export function useWorkbench() {
  const revisions = ref<Record<string, Revision>>({})
  const loading = ref(false)
  const submitting = ref(false)
  const error = ref('')
  const pollError = ref('')
  const previousRun = ref<Run | null>(null)
  const dirtySinceResult = ref(false)
  let loadGeneration = 0
  let pollGeneration = 0
  let pollTimer: ReturnType<typeof setTimeout> | undefined
  let disposed = false
  let submission: { payload: string; key: ReturnType<typeof crypto.randomUUID> } | undefined

  const selectedIds = computed(() =>
    state.mode === 'project'
      ? state.selectedProjectId
        ? [state.selectedProjectId]
        : []
      : state.selectedProjectIds,
  )
  const selectedKey = computed(() => scopeKey(state.mode, selectedIds.value))
  const currentRun = computed(() =>
    state.activeRun && matchesScope(state.activeRun, state.mode, selectedIds.value)
      ? state.activeRun
      : null,
  )
  const resultRun = computed(() => {
    if (currentRun.value?.status === 'completed' && currentRun.value.result) return currentRun.value
    return previousRun.value && matchesScope(previousRun.value, state.mode, selectedIds.value)
      ? previousRun.value
      : null
  })
  const result = computed(() => resultRun.value?.result ?? null)
  const currentRevision = computed(() => revisions.value[state.selectedProjectId])
  const busy = computed(() => submitting.value || isRunning(currentRun.value))
  const validation = computed(() => {
    if (!selectedIds.value.length) return '请先选择至少一个项目。'
    if (!state.forecastOrigin || !state.informationCutoff) return '请填写预测基准日和信息截止日。'
    if (state.informationCutoff > state.forecastOrigin) return '信息截止不得晚于预测基准日。'
    if (selectedIds.value.some((id) => !revisions.value[id])) return '所选项目的输入尚未读取完成。'
    return ''
  })

  function stopPolling() {
    pollGeneration++
    if (pollTimer) clearTimeout(pollTimer)
  }
  function remember(run: Run) {
    if (run.status === 'completed' && run.result) {
      completedByScope.set(scopeKey(run.kind, run.project_ids), run)
      if (matchesScope(run, state.mode, selectedIds.value)) previousRun.value = run
    }
  }

  async function poll(runId: string) {
    stopPolling()
    const generation = pollGeneration
    const watchedScope = selectedKey.value
    try {
      const fresh = await api.run(runId)
      if (
        disposed ||
        generation !== pollGeneration ||
        watchedScope !== selectedKey.value ||
        state.activeRun?.id !== runId
      )
        return
      state.activeRun = fresh
      remember(fresh)
      pollError.value = ''
      if (isRunning(fresh)) pollTimer = setTimeout(() => void poll(runId), 1500)
    } catch (cause) {
      if (
        !disposed &&
        generation === pollGeneration &&
        watchedScope === selectedKey.value &&
        state.activeRun?.id === runId
      ) {
        pollError.value = cause instanceof Error ? cause.message : '暂时无法读取运行状态。'
      }
    }
  }

  async function loadScope() {
    const generation = ++loadGeneration
    const ids = [...selectedIds.value]
    const mode = state.mode
    stopPolling()
    error.value = ''
    pollError.value = ''
    previousRun.value = completedByScope.get(selectedKey.value) ?? null
    if (!ids.length) {
      loading.value = false
      return
    }
    loading.value = true
    const responses = await Promise.allSettled([
      Promise.all(ids.map((id) => api.input(id))),
      api.runs(mode === 'project' ? ids[0] : undefined, ids, mode),
    ])
    if (disposed || generation !== loadGeneration) return
    const [inputs, runs] = responses
    if (inputs.status === 'fulfilled') {
      revisions.value = Object.fromEntries(inputs.value.map((input) => [input.project_id, input]))
      ids.forEach((id) => {
        if (!state.overrides[id]) state.overrides[id] = defaultOverrides()
      })
    } else {
      revisions.value = {}
      error.value = inputs.reason instanceof Error ? inputs.reason.message : '项目输入读取失败。'
    }
    if (runs.status === 'fulfilled') {
      const matching = runs.value
        .filter((run) => matchesScope(run, mode, ids))
        .sort((a, b) => b.created_at.localeCompare(a.created_at))
      const complete = matching.find((run) => run.status === 'completed' && run.result)
      if (complete) remember(complete)
      const fresh = matching[0]
      state.activeRun = fresh ?? null
      if (fresh && isRunning(fresh)) void poll(fresh.id)
    } else {
      state.activeRun = null
      error.value = runs.reason instanceof Error ? runs.reason.message : '历史运行读取失败。'
    }
    loading.value = false
  }

  function markDirty() {
    dirtySinceResult.value = true
  }
  async function refreshInputs() {
    const key = selectedKey.value
    const generation = loadGeneration
    try {
      const inputs = await Promise.all(selectedIds.value.map((id) => api.input(id)))
      if (disposed || selectedKey.value !== key || loadGeneration !== generation) return
      revisions.value = Object.fromEntries(inputs.map((input) => [input.project_id, input]))
      markDirty()
    } catch (cause) {
      if (!disposed && selectedKey.value === key && loadGeneration === generation)
        error.value = cause instanceof Error ? cause.message : '新版本读取失败，请刷新项目输入。'
    }
  }
  watch(() => [state.forecastOrigin, state.informationCutoff, editor.scenario], markDirty)
  watch(
    selectedKey,
    () => {
      dirtySinceResult.value = false
      void loadScope()
    },
    { immediate: true },
  )

  async function generate() {
    if (busy.value || loading.value) return
    if (validation.value) {
      error.value = validation.value
      return
    }
    const ids = [...selectedIds.value]
    const request: RunCreate = {
      supersedes_run_id: currentRun.value?.id ?? null,
      kind: state.mode,
      project_ids: ids,
      forecast_origin: state.forecastOrigin,
      information_cutoff: state.informationCutoff,
      scenario: editor.scenario,
      base_versions: Object.fromEntries(ids.map((id) => [id, revisions.value[id]!.version])),
      overrides: Object.fromEntries(
        ids.map((id) => [
          id,
          {
            ...(state.overrides[id] ?? defaultOverrides()),
            delivery_delays: { ...state.overrides[id]?.delivery_delays },
          },
        ]),
      ),
    }
    const payload = JSON.stringify(request)
    if (submission?.payload !== payload) submission = { payload, key: crypto.randomUUID() }
    const requestedScope = selectedKey.value
    submitting.value = true
    error.value = ''
    try {
      const run = await api.createRun(request, submission.key)
      submission = undefined
      if (disposed || requestedScope !== selectedKey.value) return
      if (currentRun.value?.status === 'completed') remember(currentRun.value)
      state.activeRun = run
      dirtySinceResult.value = false
      remember(run)
      if (isRunning(run)) void poll(run.id)
    } catch (cause) {
      if (!disposed && requestedScope === selectedKey.value) {
        error.value = cause instanceof Error ? cause.message : '提交失败，请重试。'
      }
    } finally {
      submitting.value = false
    }
  }

  async function resume() {
    if (!currentRun.value || busy.value) return
    submitting.value = true
    error.value = ''
    const id = currentRun.value.id
    try {
      const run = await api.resume(id)
      if (!disposed && state.activeRun?.id === id) {
        state.activeRun = run
        void poll(id)
      }
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : '恢复失败，请查看历史记录。'
    } finally {
      submitting.value = false
    }
  }

  function beforeUnload(event: BeforeUnloadEvent) {
    if (dirtySinceResult.value) {
      event.preventDefault()
      event.returnValue = ''
    }
  }
  onMounted(() => window.addEventListener('beforeunload', beforeUnload))
  onBeforeUnmount(() => {
    disposed = true
    loadGeneration++
    stopPolling()
    window.removeEventListener('beforeunload', beforeUnload)
  })
  return {
    editor,
    revisions,
    currentRevision,
    currentRun,
    resultRun,
    result,
    selectedIds,
    loading,
    submitting,
    error,
    pollError,
    busy,
    validation,
    dirtySinceResult,
    generate,
    resume,
    loadScope,
    refreshInputs,
    markDirty,
    refreshStatus: () => (currentRun.value ? poll(currentRun.value.id) : Promise.resolve()),
  }
}
