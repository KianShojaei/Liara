export interface TimelineEvent {
  id: string
  session_id: string
  seq: number
  ts: string
  kind: string
  payload: Record<string, any>
}

export interface Session {
  id: string
  created_at: string
  title: string
  mode: string
  project_path: string
  app_name: string
}

export interface AppSummary {
  id: string
  name: string
  platform: string
  status: string
  scale: number
  plan_id: string
  is_deployed: boolean
  allowed: boolean
  url: string
}

export interface Status {
  ok: boolean
  error?: string
  mode: 'mock' | 'live'
  llm: boolean
  balance: number
  hourly_burn: number
  runway_hours: number | null
  runway_label: string
  apps: AppSummary[]
  watcher: { running: boolean; interval?: number; apps: { app: string; session_id: string; last: any }[] }
  circuit_open: boolean
  circuit_seconds_left?: number
  last_error?: string
  api_base?: string
}

export interface AppOverview {
  app: Record<string, any>
  env_keys: string[]
  plan: { plan_id: string; ram: { amount: number }; cpu: { amount: number }; price: number } | null
  url: string
  cpu: [number, number][]
  memory: [number, number][]
  now: { cpu: number | null; memory: number | null } | null
  probe: { ok: boolean; status: number | null; latency_ms: number | null; healthy?: boolean; protected?: boolean } | null
  watching: boolean
  snapshots: { ts: number; cpu: number | null; memory: number | null; http_ok: boolean | null; latency_ms: number | null }[]
}

export interface Impact {
  cost_delta_hourly: number
  cost_delta_monthly: number
  reversibility: string
  downtime: string
  rollback_plan: string
  notes: string[]
}

export interface Proposal {
  id: string
  session_id: string
  status: string
  tool: string
  args: Record<string, any>
  tier: string
  title: string
  summary: string
  impact: Impact
  decision?: { mode: string; reasons: string[]; typed_confirmation: boolean }
  result?: any
  verification?: any
}

export interface Incident {
  id: string
  session_id: string | null
  app_name: string
  opened_at: string
  closed_at: string | null
  status: string
  trigger: string
  summary: string | null
  evidence: any
  hypotheses: Hypothesis[] | null
  remediation: { options: RemediationOption[] } | null
  fix_brief: any
}

export interface Hypothesis {
  id: string
  cause: string
  confidence: number
  evidence_refs: string[]
  explanation: string
  counter_evidence: string
  suggested_remedies: string[]
}

export interface RemediationOption {
  id: string
  title: string
  tool: string
  args: Record<string, any>
  risk: string
  cost_delta_hourly: number
  reversibility: string
  downtime: string
  rationale: string
  recommended: boolean
  requires: string
}

export interface Finding {
  kind: string
  severity: 'info' | 'warning' | 'critical'
  confidence: number
  title: string
  evidence: Record<string, any>
}

export interface Limitation {
  id: string
  title: string
  summary: string
  manual_steps?: string[]
  console_url?: string
  verify_tool?: string
}

export interface PolicyTool {
  name: string
  tier: string
  description: string
  cost_impact: string
  reversibility: string
  downtime: string
  verification: string
  enabled: boolean
}

export interface AuditRow {
  id: number
  ts: string
  actor: string
  action: string
  tool: string | null
  tier: string | null
  proposal_id: string | null
  session_id: string | null
  outcome: string
  detail: any
}

export interface ProjectAnalysis {
  path?: string
  platform: string
  platform_reason?: string
  port: number
  env_keys: string[]
  secret_env_keys?: string[]
  databases: string[]
  health_path: string
  warnings: string[]
  has_dockerfile?: boolean
  error?: string
}

export interface Project {
  name: string
  path: string
  analysis: ProjectAnalysis
}
