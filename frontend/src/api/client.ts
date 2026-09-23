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
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const response = await fetch(`/api/v1${path}`, { ...init, headers })
  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: `HTTP ${response.status}` }))
    throw new Error(error.message || error.detail || `HTTP ${response.status}`)
  }
  return response.json() as Promise<T>
}
export const api = {
  projects: () => request<Project[]>('/projects'),
  createProject: (body: S['ProjectCreate']) =>
    request<Project>('/projects', { method: 'POST', body: JSON.stringify(body) }),
  patchProject: (id: string, body: S['ProjectPatch']) =>
    request<Project>(`/projects/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  input: (id: string, revisionId?: string) =>
    request<Revision>(
      `/projects/${id}/input${revisionId ? `?revision_id=${encodeURIComponent(revisionId)}` : ''}`,
    ),
  revise: (id: string, body: S['RevisionWrite']) =>
    request<Revision>(`/projects/${id}/revisions`, { method: 'POST', body: JSON.stringify(body) }),
  previewImport: (id: string, file: File) => {
    const body = new FormData()
    body.append('file', file)
    return request<ImportPreview>(`/projects/${id}/imports/preview`, { method: 'POST', body })
  },
  confirmImport: (id: string, body: S['ImportConfirm']) =>
    request<Revision>(`/projects/${id}/imports/confirm`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  createRun: (body: RunCreate, key: string = crypto.randomUUID()) =>
    request<Run>('/runs', {
      method: 'POST',
      headers: { 'Idempotency-Key': key },
      body: JSON.stringify(body),
    }),
  runs: (projectId?: string) =>
    request<Run[]>(`/runs${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''}`),
  scopeRuns: (ids: string[]) =>
    request<Run[]>(`/runs?scope_ids=${encodeURIComponent([...ids].sort().join(','))}`),
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
