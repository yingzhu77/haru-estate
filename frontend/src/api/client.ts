import type { components } from './schema'
import type {
  Project,
  Revision,
  Run,
  RunCreate,
  Evidence,
  ImportPreview,
  Comparison,
  RunPage,
  RevisionPage,
  RevisionComparison,
} from './types'
type S = components['schemas']

export class ApiRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly requestId?: string,
  ) {
    super(requestId ? `${message}（请求编号：${requestId}）` : message)
    this.name = 'ApiRequestError'
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const response = await fetch(`/api/v1${path}`, { ...init, headers })
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: `HTTP ${response.status}` }))
    throw new ApiRequestError(
      error.message || error.detail || `HTTP ${response.status}`,
      response.status,
      error.code || 'HTTP_ERROR',
      error.request_id || response.headers.get('X-Request-ID') || undefined,
    )
  }
  return response.json() as Promise<T>
}

// Keep the key for an uncertain outcome, including a dropped success response.
// Only keys/fingerprints live in memory; business drafts are not copied to browser storage.
const pendingMutations = new Map<string, string>()
async function mutate<T>(path: string, method: string, body: unknown): Promise<T> {
  const serialized = JSON.stringify(body)
  const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(serialized))
  const fingerprint = `${method}:${path}:${Array.from(new Uint8Array(hash), (b) => b.toString(16).padStart(2, '0')).join('')}`
  const key = pendingMutations.get(fingerprint) ?? crypto.randomUUID()
  pendingMutations.set(fingerprint, key)
  try {
    const result = await request<T>(path, {
      method,
      body: serialized,
      headers: { 'Idempotency-Key': key },
    })
    pendingMutations.delete(fingerprint)
    return result
  } catch (error) {
    // Validation/conflict is a definitive rejection. Transport/5xx outcomes remain retryable.
    if (error instanceof ApiRequestError && error.status >= 400 && error.status < 500) {
      pendingMutations.delete(fingerprint)
    }
    throw error
  }
}
export const api = {
  agentStatus: () => request<S['AgentStatus']>('/agent/status'),
  agentTasks: (runId: string) =>
    request<S['AgentTask'][]>(`/agent/tasks?run_id=${encodeURIComponent(runId)}`),
  createAgentTask: (body: S['AgentCreate']) => mutate<S['AgentTask']>('/agent/tasks', 'POST', body),
  replyAgent: (id: string, body: S['AgentReply']) =>
    mutate<S['AgentTask']>(`/agent/tasks/${id}/reply`, 'POST', body),
  resumeAgent: (id: string) =>
    request<S['AgentTask']>(`/agent/tasks/${id}/resume`, { method: 'POST' }),
  parameterPreview: (body: RunCreate) =>
    request<S['EffectiveParameters'][]>('/parameters/preview', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  projects: () => request<Project[]>('/projects'),
  createProject: (body: S['ProjectCreate']) => mutate<Project>('/projects', 'POST', body),
  patchProject: (id: string, body: S['ProjectPatch']) =>
    mutate<Project>(`/projects/${id}`, 'PATCH', body),
  input: (id: string, revisionId?: string) =>
    request<Revision>(
      `/projects/${id}/input${revisionId ? `?revision_id=${encodeURIComponent(revisionId)}` : ''}`,
    ),
  revise: (id: string, body: S['RevisionWrite']) =>
    mutate<Revision>(`/projects/${id}/revisions`, 'POST', body),
  previewImport: (id: string, file: File) => {
    const body = new FormData()
    body.append('file', file)
    return request<ImportPreview>(`/projects/${id}/imports/preview`, { method: 'POST', body })
  },
  confirmImport: (id: string, body: S['ImportConfirm']) =>
    mutate<Revision>(`/projects/${id}/imports/confirm`, 'POST', body),
  createRun: (body: RunCreate, key: string = crypto.randomUUID()) =>
    request<Run>('/runs', {
      method: 'POST',
      headers: { 'Idempotency-Key': key },
      body: JSON.stringify(body),
    }),
  runs: (projectId?: string, scopeIds?: string[], kind?: 'project' | 'portfolio') => {
    const params = new URLSearchParams()
    if (projectId) params.set('project_id', projectId)
    if (scopeIds) params.set('scope_ids', [...scopeIds].sort().join(','))
    if (kind) params.set('kind', kind)
    return request<Run[]>(`/runs?${params}`)
  },
  runPage: (
    options: {
      projectId?: string
      kind?: 'project' | 'portfolio'
      offset?: number
      limit?: number
    } = {},
  ) => {
    const params = new URLSearchParams({
      offset: String(options.offset ?? 0),
      limit: String(options.limit ?? 20),
    })
    if (options.projectId) params.set('project_id', options.projectId)
    if (options.kind) params.set('kind', options.kind)
    return request<RunPage>(`/runs/page?${params}`)
  },
  revisions: (id: string, offset = 0, limit = 20) =>
    request<RevisionPage>(`/projects/${id}/revisions?offset=${offset}&limit=${limit}`),
  compareRevisions: (id: string, left: string, right: string) =>
    request<RevisionComparison>(
      `/projects/${id}/revisions/compare?left_id=${encodeURIComponent(left)}&right_id=${encodeURIComponent(right)}`,
    ),
  run: (id: string) => request<Run>(`/runs/${id}`),
  resume: (id: string) => request<Run>(`/runs/${id}/resume`, { method: 'POST' }),
  evidence: (id: string, metric = 'profit', month?: string) =>
    request<Evidence>(
      `/runs/${id}/evidence?metric=${encodeURIComponent(metric)}${month ? `&month=${encodeURIComponent(month)}` : ''}`,
    ),
  compare: (left: string, right: string) =>
    request<Comparison>(
      `/compare?left_id=${encodeURIComponent(left)}&right_id=${encodeURIComponent(right)}`,
    ),
}
