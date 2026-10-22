import { useState } from 'react'
import { api } from '../api'
import { CHECK_NAMES, DOWNTIME, PROPOSAL_STATUS, REVERSIBILITY, RISK, TIER, checkDetail, signed, time } from '../format'
import type { Proposal } from '../types'
import { Button, Card, Check, Chip, Ltr } from './ui'

export function ProposalCard({ proposal, ts }: { proposal: Proposal; ts?: string }) {
  const [busy, setBusy] = useState<'approve' | 'reject' | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [typed, setTyped] = useState('')
  const envArgs: Record<string, string> = proposal.tool === 'set_env' ? proposal.args.variables ?? {} : {}
  const [envValues, setEnvValues] = useState<Record<string, string>>(() => Object.fromEntries(Object.entries(envArgs).map(([k, v]) => [k, v === '<hidden>' ? '' : v])))
  const status = PROPOSAL_STATUS[proposal.status] ?? { label: proposal.status, tone: 'neutral' as const }
  const tier = TIER[proposal.tier] ?? { label: proposal.tier, tone: 'neutral' as const }
  const pending = proposal.status === 'pending_approval'
  const impact = proposal.impact ?? ({} as Proposal['impact'])
  const needsTyped = proposal.decision?.typed_confirmation || proposal.tier === 'T3'
  const verification = proposal.verification
  const failed = proposal.status.includes('fail') || proposal.status === 'blocked'

  const act = async (kind: 'approve' | 'reject', fn: () => Promise<unknown>) => {
    setBusy(kind)
    setErr(null)
    try {
      await fn()
    } catch (e) {
      setErr(String((e as Error).message))
    } finally {
      setBusy(null)
    }
  }

  const approve = () =>
    act('approve', () =>
      api.approve(proposal.id, {
        typed_confirmation: needsTyped ? typed : undefined,
        edited_args: proposal.tool === 'set_env' ? { variables: envValues } : undefined,
      }),
    )

  const summaryLines = (proposal.summary ?? '').split('\n').filter(Boolean)

  return (
    <Card
      tone={pending ? 'accent' : proposal.status === 'verified' ? 'success' : failed ? 'error' : 'default'}
      title={proposal.title}
      icon="🛡️"
      meta={
        <>
          <Chip tone={tier.tone} title="سطح ریسک عملیات">{tier.label}</Chip>
          <Chip tone={status.tone}>{['running', 'executed', 'approved'].includes(proposal.status) && <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-current" />}{status.label}</Chip>
        </>
      }
    >
      {summaryLines.length > 1 ? (
        <ol className="space-y-1 text-sm">
          {summaryLines.map((l, i) => (
            <li key={i} className="flex gap-2">
              <span className="text-muted">{l.match(/^\d+\./) ? '' : '•'}</span>
              <span>{l}</span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="text-sm">{proposal.summary}</p>
      )}

      <dl className="mt-3 grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
        <Impact label="هزینه / ساعت" value={impact.cost_delta_hourly ? `${signed(impact.cost_delta_hourly)} تومان` : 'بدون تغییر'} tone={impact.cost_delta_hourly > 0 ? 'warning' : undefined} />
        <Impact label="هزینه / ماه" value={impact.cost_delta_monthly ? `${signed(impact.cost_delta_monthly)} تومان` : '—'} />
        <Impact label="بازگشت‌پذیری" value={REVERSIBILITY[impact.reversibility] ?? impact.reversibility ?? '—'} tone={impact.reversibility === 'irreversible' ? 'danger' : undefined} />
        <Impact label="قطعی سرویس" value={DOWNTIME[impact.downtime] ?? impact.downtime ?? '—'} tone={impact.downtime === 'yes' ? 'danger' : undefined} />
      </dl>
      {(impact.notes ?? []).filter(Boolean).length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {impact.notes.filter(Boolean).map((n) => (
            <Chip key={n} tone="outline">{n.replace(/^(?:risk|ریسک):\s*(low|medium|high)$/i, (_m, r) => RISK[r.toLowerCase()] ?? n)}</Chip>
          ))}
        </div>
      )}
      {impact.rollback_plan && (
        <div className="mt-3 flex gap-2 rounded-xl bg-raised/60 px-3 py-2 text-xs">
          <span aria-hidden>↩️</span>
          <span><span className="font-medium">برنامه‌ی بازگشت:</span> {impact.rollback_plan}</span>
        </div>
      )}

      {proposal.tool === 'set_env' && pending && (
        <div className="mt-3 space-y-2">
          {Object.keys(envValues).map((k) => (
            <label key={k} className="flex items-center gap-2 text-sm">
              <Ltr className="w-40 shrink-0 text-xs">{k}</Ltr>
              <input className="input" dir="ltr" type={/SECRET|TOKEN|PASS|KEY/i.test(k) ? 'password' : 'text'} value={envValues[k]} onChange={(e) => setEnvValues({ ...envValues, [k]: e.target.value })} placeholder="مقدار" />
            </label>
          ))}
        </div>
      )}

      {needsTyped && pending && (
        <label className="mt-3 block text-sm">
          برای تأیید، نام برنامه را عیناً بنویسید:
          <input className="input mono mt-1" dir="ltr" value={typed} onChange={(e) => setTyped(e.target.value)} />
        </label>
      )}

      {proposal.decision?.mode === 'blocked' && <div className="mt-3 rounded-xl border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-300">{proposal.decision.reasons.join('؛ ')}</div>}
      {err && <div className="mt-3 text-sm text-rose-400">{err}</div>}

      {pending && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button variant="primary" loading={busy === 'approve'} disabled={busy != null} onClick={approve}>
            ✓ تأیید و اجرا
          </Button>
          <Button variant="ghost" loading={busy === 'reject'} disabled={busy != null} onClick={() => act('reject', () => api.reject(proposal.id, 'کاربر رد کرد'))}>
            رد کردن
          </Button>
          <span className="text-[11px] text-muted">بعد از اجرا نتیجه بررسی و اینجا نشان داده می‌شود.</span>
        </div>
      )}
      {proposal.result?.error && <div className="mt-3 rounded-xl border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-300">خطا: {proposal.result.error}</div>}
      {verification?.steps && (
        <ul className="mt-3 grid gap-1 text-xs sm:grid-cols-2">
          {verification.steps.map((s: any, i: number) => (
            <li key={i} className="flex items-center gap-2">
              <Check ok={!!s.ok} />
              <span className="font-medium">{CHECK_NAMES[s.name] ?? s.name}</span>
              <span className="text-muted">{checkDetail(s.detail)}</span>
            </li>
          ))}
        </ul>
      )}
      {proposal.result?.url && !proposal.result.error && (
        <a className="mt-3 block text-sm text-emerald-500 hover:underline" href={proposal.result.url} target="_blank" rel="noreferrer" dir="ltr">
          {proposal.result.url}
        </a>
      )}
      {ts && <div className="mt-3 text-[10px] text-muted">{time(ts)}</div>}
    </Card>
  )
}

function Impact({ label, value, tone }: { label: string; value: string; tone?: 'warning' | 'danger' }) {
  const c = tone === 'danger' ? 'text-rose-400' : tone === 'warning' ? 'text-amber-400' : ''
  return (
    <div className="rounded-xl border border-line bg-bg/50 px-3 py-2">
      <dt className="text-[11px] text-muted">{label}</dt>
      <dd className={`font-medium ${c}`}>{value}</dd>
    </div>
  )
}
