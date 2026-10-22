import type { AppOverview, AuditRow, Incident, Limitation, PolicyTool, Project, Proposal, Session, Status, TimelineEvent } from './types'

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const data = await res.json()
      detail = data.detail ?? JSON.stringify(data)
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status}: ${detail}`)
  }
  const text = await res.text()
  return (text ? JSON.parse(text) : {}) as T
}

const get = <T,>(url: string) => request<T>('GET', url)
const del = <T,>(url: string) => request<T>('DELETE', url)

/** Multipart upload with progress (fetch has no upload progress; XHR does). */
export function uploadProject(file: File, name: string, onProgress: (ratio: number) => void): Promise<Project> {
  return new Promise((resolve, reject) => {
    const form = new FormData()
    form.append('file', file)
    if (name) form.append('name', name)
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/projects/upload')
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total)
    xhr.onload = () => {
      try {
        const data = JSON.parse(xhr.responseText || '{}')
        if (xhr.status >= 200 && xhr.status < 300) resolve(data as Project)
        else reject(new Error(`${xhr.status}: ${data.detail ?? xhr.statusText}`))
      } catch (e) {
        reject(e)
      }
    }
    xhr.onerror = () => reject(new Error('آپلود ناموفق بود'))
    xhr.send(form)
  })
}
const post = <T,>(url: string, body?: unknown) => request<T>('POST', url, body ?? {})

export const api = {
  createSession: (title: string) => post<Session>('/api/sessions', { title }),
  listSessions: () => get<Session[]>('/api/sessions'),
  timeline: (id: string, after = 0) => get<TimelineEvent[]>(`/api/sessions/${id}/timeline?after=${after}`),
  sendMessage: (id: string, text: string, app?: string, path?: string) =>
    post<{ accepted: boolean }>(`/api/sessions/${id}/messages`, { text, app: app ?? '', path: path ?? '' }),
  approve: (id: string, body: { typed_confirmation?: string; edited_args?: Record<string, any> }) =>
    post<Proposal>(`/api/proposals/${id}/approve`, body),
  reject: (id: string, reason = '') => post<Proposal>(`/api/proposals/${id}/reject`, { reason }),
  wizardEnv: (id: string, values: Record<string, string>) => post(`/api/sessions/${id}/wizard/env`, { values }),
  wizardEnvDefaults: (id: string) => get<{ values: Record<string, string>; sources: Record<string, string> }>(`/api/sessions/${id}/wizard/env-defaults`),
  wizardPlan: (id: string, plan_id: string) => post(`/api/sessions/${id}/wizard/plan`, { plan_id }),
  wizardResume: (id: string) => post(`/api/sessions/${id}/wizard/resume`),
  manualStepDone: (session_id: string, limitation_id: string, context: Record<string, any>) =>
    post('/api/manual-steps/done', { session_id, limitation_id, context }),
  status: () => get<Status>('/api/status'),
  appOverview: (app: string) => get<AppOverview>(`/api/apps/${app}/overview`),
  incidents: () => get<Incident[]>('/api/incidents'),
  incident: (id: string) => get<Incident>(`/api/incidents/${id}`),
  verifyIncident: (id: string) => post<any>(`/api/incidents/${id}/verify`),
  closeIncident: (id: string) => post<Incident>(`/api/incidents/${id}/close`),
  fixBrief: (id: string) => get<any>(`/api/incidents/${id}/fix-brief`),
  runCodingAgent: (id: string, project_path: string, demo_patch: boolean) =>
    post<any>(`/api/incidents/${id}/run-coding-agent`, { project_path, demo_patch }),
  remediate: (incident_id: string, option_id: string, session_id: string, edited_args?: Record<string, any>) =>
    post<Proposal & { session_id: string }>(`/api/incidents/${incident_id}/remediate`, { option_id, session_id, edited_args }),
  audit: (limit = 200) => get<AuditRow[]>(`/api/audit?limit=${limit}`),
  limitations: () => get<Limitation[]>('/api/limitations'),
  policyTools: () => get<PolicyTool[]>('/api/policy/tools'),
  setWatch: (app: string, enabled: boolean, session_id: string) =>
    post<any>(`/api/watcher/${app}?enabled=${enabled}&session_id=${session_id}`),
  projects: () => get<Project[]>('/api/projects'),
  importGit: (url: string, branch: string, name: string) => post<Project>('/api/projects/git', { url, branch, name }),
  registerLocal: (path: string) => post<Project>('/api/projects/local', { path }),
  deleteProject: (name: string) => del<{ deleted: string }>(`/api/projects/${encodeURIComponent(name)}`),
  wizardStart: (session_id: string, path: string, app: string, plan_id = '') =>
    post<{ accepted: boolean }>(`/api/sessions/${session_id}/wizard/start`, { path, app, plan_id }),
  investigate: (session_id: string, app: string) =>
    post(`/api/sessions/${session_id}/investigate`, { app, window_minutes: 30, health_path: '/' }),
}
