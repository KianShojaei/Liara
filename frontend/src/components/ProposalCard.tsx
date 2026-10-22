import { useState } from 'react'
import { api } from '../api'
import { DOWNTIME, PROPOSAL_STATUS, REVERSIBILITY, RISK, TIER, signed } from '../format'
import type { Proposal } from '../types'
import { Chip, Card } from './ui'

export function ProposalCard({ proposal }: { proposal: Proposal }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [typed, setTyped] = useState('')
  const envArgs: Record<string, string> = proposal.tool === 'set_env' ? proposal.args.variables ?? {} : {}
  const [envValues, setEnvValues] = useState<Record<string, string>>(() => Object.fromEntries(Object.entries(envArgs).map(([k, v]) => [k, v === '<hidden>' ? '' : v])))
  const status = PROPOSAL_STATUS[proposal.status] ?? { label: proposal.status, cls: '' }
  const tier = TIER[proposal.tier] ?? { label: proposal.tier, cls: '' }
  const pending = proposal.status === 'pending_approval'
  const impact = proposal.impact ?? ({} as Proposal['impact'])
  const needsTyped = proposal.decision?.typed_confirmation || proposal.tier === 'T3'

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    setErr(null)
    try {
      await fn()
    } catch (e) {
      setErr(String((e as Error).message))
    } finally {
      setBusy(false)
    }
  }

  const approve = () =>
    act(() =>
      api.approve(proposal.id, {
        typed_confirmation: needsTyped ? typed : undefined,
        edited_args: proposal.tool === 'set_env' ? { variables: envValues } : undefined,
      }),
    )

  return (
    <Card tone={pending ? 'warning' : proposal.status === 'verified' ? 'success' : proposal.status.includes('fail') || proposal.status === 'blocked' ? 'error' : 'default'}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 font-semibold">
          <span aria-hidden>🛡️</span>
          <span>{proposal.title}</span>
        </div>
        <div className="flex gap-1">
          <Chip cls={tier.cls} title="سطح ریسک عملیات">{tier.label}</Chip>
          <Chip cls={status.cls}>{status.label}</Chip>
        </div>
      </div>
      <pre className="mt-2 whitespace-pre-wrap font-sans text-sm leading-6">{proposal.summary}</pre>

      <div className="mt-3 flex flex-wrap gap-1.5 text-xs">
        <Chip title="تغییر هزینه">
          هزینه: {impact.cost_delta_hourly ? `${signed(impact.cost_delta_hourly)} تومان/ساعت (${signed(impact.cost_delta_monthly)}/ماه)` : 'بدون تغییر'}
        </Chip>
        <Chip>{REVERSIBILITY[impact.reversibility] ?? impact.reversibility}</Chip>
        <Chip>{DOWNTIME[impact.downtime] ?? impact.downtime}</Chip>
        {(impact.notes ?? []).filter(Boolean).map((n) => (
          <Chip key={n}>{n.replace(/^risk:\s*(low|medium|high)$/i, (_m, r) => RISK[r.toLowerCase()] ?? n)}</Chip>
        ))}
      </div>
      {impact.rollback_plan && <div className="mt-2 text-xs text-slate-600 dark:text-slate-300">↩️ بازگشت: {impact.rollback_plan}</div>}

      {proposal.tool === 'set_env' && pending && (
        <div className="mt-3 space-y-2">
          {Object.keys(envValues).map((k) => (
            <label key={k} className="flex items-center gap-2 text-sm">
              <span className="mono w-40 shrink-0 text-xs">{k}</span>
              <input className="input" type={/SECRET|TOKEN|PASS|KEY/i.test(k) ? 'password' : 'text'} value={envValues[k]} onChange={(e) => setEnvValues({ ...envValues, [k]: e.target.value })} placeholder="مقدار" />
            </label>
          ))}
        </div>
      )}

      {needsTyped && pending && (
        <label className="mt-3 block text-sm">
          برای تأیید، نام برنامه را عیناً بنویسید:
          <input className="input mono mt-1" value={typed} onChange={(e) => setTyped(e.target.value)} />
        </label>
      )}

      {proposal.decision?.mode === 'blocked' && <div className="mt-2 text-sm text-rose-600">{proposal.decision.reasons.join('؛ ')}</div>}
      {err && <div className="mt-2 text-sm text-rose-600">{err}</div>}

      {pending && (
        <div className="mt-3 flex gap-2">
          <button className="btn-primary" disabled={busy} onClick={approve}>
            ✓ تأیید و اجرا
          </button>
          <button className="btn-ghost" disabled={busy} onClick={() => act(() => api.reject(proposal.id, 'کاربر رد کرد'))}>
            رد کردن
          </button>
        </div>
      )}
      {proposal.result?.error && <div className="mt-2 text-sm text-rose-600">خطا: {proposal.result.error}</div>}
      {proposal.result?.url && !proposal.result.error && (
        <a className="mt-2 block text-sm text-emerald-700 underline" href={proposal.result.url} target="_blank" rel="noreferrer">
          {proposal.result.url}
        </a>
      )}
    </Card>
  )
}
