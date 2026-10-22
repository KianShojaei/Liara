import { useEffect, useMemo, useRef } from 'react'
import type { Proposal, TimelineEvent } from '../types'
import { EvidenceCard, FixBriefCard, HypothesesCard, IncidentBanner, LogsCard, PatchCard, RemediationCard, VerificationCard } from './IncidentCards'
import { ProposalCard } from './ProposalCard'
import { StepperCard, type StepState } from './Stepper'
import { Card } from './ui'
import { AnalysisCard, EnvFormCard, ManualStepCard, PlanOptionsCard } from './WizardCards'

type Block =
  | { kind: 'event'; event: TimelineEvent }
  | { kind: 'proposal'; proposal: Proposal; seq: number; id: string }
  | { kind: 'stepper'; steps: StepState[]; logs: string[]; seq: number; id: string }

/** Folds proposal_update into proposals and step/deploy_log into one stepper block. */
function fold(events: TimelineEvent[]): Block[] {
  const blocks: Block[] = []
  const proposals = new Map<string, Proposal>()
  let stepper: Extract<Block, { kind: 'stepper' }> | null = null
  for (const e of events) {
    const p = e.payload
    switch (e.kind) {
      case 'proposal': {
        const prop = p as Proposal
        proposals.set(prop.id, prop)
        blocks.push({ kind: 'proposal', proposal: prop, seq: e.seq, id: e.id })
        stepper = null
        break
      }
      case 'proposal_update': {
        const prev = proposals.get(p.id)
        if (prev) {
          const next = { ...prev, status: p.status, result: p.result ?? prev.result }
          if (p.error) next.result = { ...(next.result ?? {}), error: p.error }
          proposals.set(p.id, next)
          const idx = blocks.findIndex((b) => b.kind === 'proposal' && b.proposal.id === p.id)
          if (idx >= 0) blocks[idx] = { ...(blocks[idx] as Extract<Block, { kind: 'proposal' }>), proposal: next }
        }
        break
      }
      case 'step': {
        if (!stepper) {
          stepper = { kind: 'stepper', steps: [], logs: [], seq: e.seq, id: e.id }
          blocks.push(stepper)
        }
        const existing = stepper.steps.find((s) => s.name === p.name)
        if (existing) {
          existing.status = p.status
          existing.detail = p.detail || existing.detail
        } else stepper.steps.push({ name: p.name, status: p.status, detail: p.detail ?? '' })
        break
      }
      case 'deploy_log': {
        if (!stepper) {
          stepper = { kind: 'stepper', steps: [], logs: [], seq: e.seq, id: e.id }
          blocks.push(stepper)
        }
        stepper.logs.push(p.line)
        break
      }
      case 'verification':
        if (p.proposal_id) {
          const prev = proposals.get(p.proposal_id)
          if (prev) {
            const next = { ...prev, status: p.status ?? prev.status, verification: p }
            proposals.set(p.proposal_id, next)
            const idx = blocks.findIndex((b) => b.kind === 'proposal' && b.proposal.id === p.proposal_id)
            if (idx >= 0) blocks[idx] = { ...(blocks[idx] as Extract<Block, { kind: 'proposal' }>), proposal: next }
          }
        }
        blocks.push({ kind: 'event', event: e })
        break
      default:
        blocks.push({ kind: 'event', event: e })
    }
  }
  return blocks
}

export function Timeline({ events, sessionId, app }: { events: TimelineEvent[]; sessionId: string; app?: string }) {
  const blocks = useMemo(() => fold(events), [events])
  const bottom = useRef<HTMLDivElement>(null)
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [events.length])

  const working = events.length > 0 && events[events.length - 1].kind === 'status'

  return (
    <div className="space-y-3 pb-4">
      {blocks.length === 0 && (
        <div className="card text-center text-sm text-slate-500">
          سلام! من دستیار عملیاتی شما برای لیارا هستم. بگویید چه کاری انجام دهم؛ قبل از هر تغییر مهم از شما تأیید می‌گیرم.
        </div>
      )}
      {blocks.map((b) => {
        if (b.kind === 'proposal') return <ProposalCard key={b.id} proposal={b.proposal} />
        if (b.kind === 'stepper') return <StepperCard key={b.id} steps={b.steps} logs={b.logs} />
        return <EventCard key={b.event.id} e={b.event} sessionId={sessionId} app={app} />
      })}
      {working && (
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <span className="inline-block h-2 w-2 animate-ping rounded-full bg-emerald-500" /> در حال کار…
        </div>
      )}
      <div ref={bottom} />
    </div>
  )
}

function EventCard({ e, sessionId, app }: { e: TimelineEvent; sessionId: string; app?: string }) {
  const p = e.payload
  switch (e.kind) {
    case 'message':
      return <Message role={p.role} text={p.text} />
    case 'status':
      return <div className="text-xs text-slate-500">⏳ {p.text}</div>
    case 'notice':
      return (
        <div className="rounded-xl border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-900 dark:border-sky-900 dark:bg-sky-900/20 dark:text-sky-100">
          ℹ️ اقدام کم‌ریسک به‌صورت خودکار انجام شد: {p.title}
          {p.detail && <div>{p.detail}</div>}
        </div>
      )
    case 'error':
      return (
        <Card tone="error" title="خطا" icon="⚠️">
          <div className="text-sm">{p.text}</div>
          {p.steps && <ul className="mt-1 text-xs">{p.steps.map((s: any, i: number) => <li key={i}>{s.ok ? '✓' : '✗'} {s.name}: {s.detail}</li>)}</ul>}
        </Card>
      )
    case 'success':
      return (
        <Card tone="success" title={p.text} icon="🎉">
          {p.url && (
            <a className="text-sm text-emerald-700 underline" href={p.url} target="_blank" rel="noreferrer">
              {p.url}
            </a>
          )}
        </Card>
      )
    case 'analysis':
      return <AnalysisCard p={p} />
    case 'plan_options':
      return <PlanOptionsCard p={p} sessionId={sessionId} />
    case 'manual_step':
      return <ManualStepCard p={p} sessionId={sessionId} app={app} />
    case 'env_form':
      return <EnvFormCard p={p} sessionId={sessionId} />
    case 'verification':
      return p.proposal_id ? null : <VerificationCard p={p} />
    case 'incident':
      return <IncidentBanner p={p} />
    case 'evidence':
      return <EvidenceCard p={p} />
    case 'hypotheses':
      return <HypothesesCard p={p} />
    case 'remediation':
      return <RemediationCard p={p} sessionId={sessionId} />
    case 'logs':
      return <LogsCard p={p} />
    case 'fix_brief':
      return <FixBriefCard p={p} />
    case 'patch':
      return <PatchCard p={p} />
    case 'verify_round':
      return <div className="text-xs text-slate-500">🔁 دور {p.round}: پاسخ موفق {p.probe_success == null ? '—' : Math.round(p.probe_success * 100) + '٪'} · حافظه {p.memory ? Math.round(p.memory / 1024 / 1024) + ' MB' : '—'}</div>
    default:
      return null
  }
}

function Message({ role, text }: { role: string; text: string }) {
  const user = role === 'user'
  return (
    <div className={`flex ${user ? 'justify-start' : 'justify-end'}`}>
      <div className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2 text-sm leading-7 ${user ? 'bg-emerald-600 text-white' : 'bg-white shadow-sm dark:bg-slate-900'}`}>{text}</div>
    </div>
  )
}
