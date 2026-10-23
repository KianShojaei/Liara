import { AlertIcon, BotIcon, CheckCircleIcon, InfoIcon, RefreshIcon, RocketIcon, UserIcon } from './icons'
import { useEffect, useMemo, useRef, useState } from 'react'
import { CHECK_NAMES, checkDetail, time } from '../format'
import type { Project, Proposal, TimelineEvent } from '../types'
import { EvidenceCard, FixBriefCard, HypothesesCard, IncidentBanner, LogsCard, PatchCard, RemediationCard, VerificationCard } from './IncidentCards'
import { IntakePanel, ProjectCard } from './Projects'
import { ProposalCard } from './ProposalCard'
import { StepperCard, type StepState } from './Stepper'
import { Button, Card, Check } from './ui'
import { AnalysisCard, EnvFormCard, ManualStepCard, PlanOptionsCard } from './WizardCards'

type Block =
  | { kind: 'event'; event: TimelineEvent }
  | { kind: 'proposal'; proposal: Proposal; seq: number; id: string; ts: string }
  | { kind: 'stepper'; steps: StepState[]; logs: string[]; seq: number; id: string }

/** Folds proposal_update into proposals and step/deploy_log into one stepper block. */
function fold(events: TimelineEvent[]): Block[] {
  const blocks: Block[] = []
  const proposals = new Map<string, Proposal>()
  let stepper: Extract<Block, { kind: 'stepper' }> | null = null
  const patch = (id: string, next: Proposal) => {
    proposals.set(id, next)
    const idx = blocks.findIndex((b) => b.kind === 'proposal' && b.proposal.id === id)
    if (idx >= 0) blocks[idx] = { ...(blocks[idx] as Extract<Block, { kind: 'proposal' }>), proposal: next }
  }
  for (const e of events) {
    const p = e.payload
    switch (e.kind) {
      case 'proposal': {
        const prop = p as Proposal
        proposals.set(prop.id, prop)
        blocks.push({ kind: 'proposal', proposal: prop, seq: e.seq, id: e.id, ts: e.ts })
        stepper = null
        break
      }
      case 'proposal_update': {
        const prev = proposals.get(p.id)
        if (prev) {
          const next = { ...prev, status: p.status, result: p.result ?? prev.result }
          if (p.error) next.result = { ...(next.result ?? {}), error: p.error }
          patch(p.id, next)
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
          if (prev) patch(p.proposal_id, { ...prev, status: p.status ?? prev.status, verification: p })
        }
        blocks.push({ kind: 'event', event: e })
        break
      default:
        blocks.push({ kind: 'event', event: e })
    }
  }
  return blocks
}

interface Props {
  events: TimelineEvent[]
  sessionId: string
  app?: string
  onStartDeploy: (path: string, app: string) => Promise<void>
}

export function Timeline({ events, sessionId, app, onStartDeploy }: Props) {
  const blocks = useMemo(() => fold(events), [events])
  const bottom = useRef<HTMLDivElement>(null)
  const [intake, setIntake] = useState<Project | null>(null)
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [events.length])

  const working = events.length > 0 && events[events.length - 1].kind === 'status'

  return (
    <div className="space-y-3 pb-4">
      {blocks.length === 0 && (
        <div className="space-y-3 animate-rise">
          <div className="rounded-2xl border border-line bg-gradient-to-br from-emerald-500/10 via-surface to-surface p-5">
            <div className="text-base font-semibold">سلام! من دستیار عملیاتی شما برای لیارا هستم.</div>
            <p className="mt-1 text-sm text-muted">پروژه‌تان را وارد کنید تا دیپلوی کنم، یا در مورد وضعیت و مشکلات سایت بپرسید. هیچ تغییر مهمی بدون تأیید شما انجام نمی‌شود.</p>
          </div>
          <Card title="شروع دیپلوی" icon={<RocketIcon size={18} />}>
            {!intake ? <IntakePanel compact onReady={setIntake} /> : null}
            {intake && (
              <div className="space-y-2">
                <ProjectCard project={intake} onDeploy={onStartDeploy} />
                <Button variant="ghost" size="sm" onClick={() => setIntake(null)}>
                  پروژه‌ی دیگر
                </Button>
              </div>
            )}
          </Card>
        </div>
      )}
      {blocks.map((b) => {
        if (b.kind === 'proposal') return <ProposalCard key={b.id} proposal={b.proposal} ts={b.ts} />
        if (b.kind === 'stepper') return <StepperCard key={b.id} steps={b.steps} logs={b.logs} />
        return <EventCard key={b.event.id} e={b.event} sessionId={sessionId} app={app} />
      })}
      {working && <Thinking />}
      <div ref={bottom} />
    </div>
  )
}

function Thinking() {
  return (
    <div className="flex items-end gap-2">
      <Avatar role="assistant" />
      <div className="skeleton h-9 w-40 rounded-2xl" aria-label="در حال کار" />
    </div>
  )
}

function Avatar({ role }: { role: 'user' | 'assistant' }) {
  return (
    <span className={`grid h-7 w-7 shrink-0 place-items-center rounded-full text-sm ${role === 'user' ? 'bg-emerald-500 text-white dark:text-slate-950' : 'bg-raised'}`} aria-hidden>
      {role === 'user' ? <UserIcon size={14} /> : <BotIcon size={14} />}
    </span>
  )
}

function Message({ role, text, ts }: { role: string; text: string; ts: string }) {
  const user = role === 'user'
  return (
    <div className={`flex items-end gap-2 ${user ? 'flex-row-reverse' : ''}`}>
      <Avatar role={user ? 'user' : 'assistant'} />
      <div className={`max-w-[85%] ${user ? 'items-end' : 'items-start'} flex flex-col gap-0.5`}>
        <div className={`whitespace-pre-wrap rounded-2xl px-4 py-2 text-sm leading-7 ${user ? 'rounded-bl-md bg-emerald-500 text-white dark:text-slate-950' : 'rounded-br-md border border-line bg-surface'}`}>{text}</div>
        <span className="px-1 text-[10px] text-muted">{time(ts)}</span>
      </div>
    </div>
  )
}

function EventCard({ e, sessionId, app }: { e: TimelineEvent; sessionId: string; app?: string }) {
  const p = e.payload
  switch (e.kind) {
    case 'message':
      return <Message role={p.role} text={p.text} ts={e.ts} />
    case 'status':
      return (
        <div className="flex items-center gap-2 px-9 text-xs text-muted">
          <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
          {p.text}
        </div>
      )
    case 'notice':
      return (
        <div className="mr-9 rounded-xl border border-sky-400/30 bg-sky-400/10 px-3 py-2 text-xs text-sky-700 dark:text-sky-200">
          <InfoIcon size={14} className="ml-1 text-sky-400" /> اقدام کم‌ریسک به‌صورت خودکار انجام شد: {p.title}
          {p.detail && <div className="mt-0.5 opacity-80">{p.detail}</div>}
        </div>
      )
    case 'error':
      return (
        <Card tone="error" title="خطا" icon={<AlertIcon size={18} className="text-rose-500" />}>
          <div className="text-sm">{p.text}</div>
          {p.steps && (
            <ul className="mt-2 space-y-1 text-xs">
              {p.steps.map((s: any, i: number) => (
                <li key={i} className="flex items-center gap-2">
                  <Check ok={!!s.ok} /> {CHECK_NAMES[s.name] ?? s.name}: {checkDetail(s.detail)}
                </li>
              ))}
            </ul>
          )}
        </Card>
      )
    case 'success':
      return (
        <Card tone="success" title={p.text} icon={<CheckCircleIcon size={18} className="text-emerald-500" />}>
          {p.url && (
            <a className="btn-primary mt-1 w-full" href={p.url} target="_blank" rel="noreferrer" dir="ltr">
              باز کردن سایت ↗ <span className="mono opacity-90">{p.url}</span>
            </a>
          )}
          {p.steps && (
            <ul className="mt-3 grid gap-1 text-xs sm:grid-cols-2">
              {p.steps.map((s: any, i: number) => (
                <li key={i} className="flex items-center gap-2">
                  <Check ok={!!s.ok} /> {CHECK_NAMES[s.name] ?? s.name}: {checkDetail(s.detail)}
                </li>
              ))}
            </ul>
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
      return (
        <div className="px-9 text-xs text-muted">
          <RefreshIcon size={12} className="ml-1" /> دور {p.round}: پاسخ موفق {p.probe_success == null ? '—' : Math.round(p.probe_success * 100) + '٪'} · حافظه {p.memory ? Math.round(p.memory / 1024 / 1024) + ' MB' : '—'}
        </div>
      )
    default:
      return null
  }
}
