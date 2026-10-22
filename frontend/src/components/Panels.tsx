import { useEffect, useState } from 'react'
import { api } from '../api'
import { PROPOSAL_STATUS, TIER, time } from '../format'
import type { AuditRow, Incident, Limitation, PolicyTool } from '../types'
import { EvidenceCard, HypothesesCard, PatchCard, RemediationCard, VerificationCard } from './IncidentCards'
import { Card, Chip } from './ui'

export function AuditPanel() {
  const [rows, setRows] = useState<AuditRow[]>([])
  useEffect(() => {
    api.audit(200).then(setRows).catch(() => undefined)
  }, [])
  const ACTOR: Record<string, string> = { agent: 'دستیار', human: 'شما', system: 'سیستم', verifier: 'بررسی‌کننده', investigator: 'تحلیل‌گر', watcher: 'پایشگر' }
  return (
    <Card title="دفتر ثبت وقایع (فقط افزودنی)" icon="📒">
      <p className="mb-2 text-xs text-slate-500">هر پیشنهاد، تأیید، اجرا و بررسی اینجا ثبت می‌شود و قابل حذف نیست.</p>
      <div className="max-h-[70vh] overflow-auto">
        <table className="w-full text-xs">
          <thead className="text-slate-500">
            <tr><th className="py-1 text-right">زمان</th><th className="text-right">چه کسی</th><th className="text-right">کار</th><th className="text-right">ابزار</th><th className="text-right">نتیجه</th></tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-slate-100 dark:border-slate-800">
                <td className="mono py-1">{time(r.ts)}</td>
                <td>{ACTOR[r.actor] ?? r.actor}</td>
                <td>{r.action}</td>
                <td className="mono">{r.tool ?? ''} {r.tier && <Chip cls={TIER[r.tier]?.cls}>{r.tier}</Chip>}</td>
                <td><Chip cls={PROPOSAL_STATUS[r.outcome]?.cls}>{PROPOSAL_STATUS[r.outcome]?.label ?? r.outcome}</Chip></td>
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.length && <div className="text-sm text-slate-500">هنوز چیزی ثبت نشده.</div>}
      </div>
    </Card>
  )
}

export function LimitationsPanel() {
  const [items, setItems] = useState<Limitation[]>([])
  useEffect(() => {
    api.limitations().then(setItems).catch(() => undefined)
  }, [])
  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-600 dark:text-slate-300">این کارها از طریق API لیارا ممکن نیست؛ دستیار برای هرکدام یک کارت «کار دستی» با مراحل دقیق نشان می‌دهد.</p>
      {items.map((l) => (
        <Card key={l.id} title={l.title} icon="🖐️">
          <p className="text-sm">{l.summary}</p>
          {l.manual_steps && (
            <ol className="mt-2 list-decimal space-y-0.5 pr-5 text-sm">
              {l.manual_steps.map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ol>
          )}
          {l.console_url && (
            <a className="mt-2 inline-block text-xs text-emerald-700 underline" href={l.console_url} target="_blank" rel="noreferrer">
              {l.console_url}
            </a>
          )}
        </Card>
      ))}
    </div>
  )
}

export function PolicyPanel() {
  const [tools, setTools] = useState<PolicyTool[]>([])
  useEffect(() => {
    api.policyTools().then(setTools).catch(() => undefined)
  }, [])
  const DESC: Record<string, string> = {
    T0: 'فقط خواندن؛ خودکار اجرا می‌شود.',
    T1: 'تغییر کم‌ریسک؛ خودکار با اطلاع‌رسانی.',
    T2: 'تغییر وضعیت؛ فقط با تأیید شما، سپس اجرا و بررسی.',
    T3: 'محافظت‌شده (حذف، غیرفعال کردن SSL، کاهش پلن)؛ به‌صورت پیش‌فرض خاموش و نیازمند تایپ تأیید.',
  }
  return (
    <div className="space-y-3">
      {(['T0', 'T1', 'T2', 'T3'] as const).map((t) => (
        <Card key={t} title={`${t} — ${TIER[t].label}`} icon="🛡️">
          <p className="mb-2 text-xs text-slate-500">{DESC[t]}</p>
          <ul className="space-y-1 text-sm">
            {tools.filter((x) => x.tier === t).map((x) => (
              <li key={x.name} className="flex flex-wrap items-center gap-2">
                <span className="mono text-xs">{x.name}</span>
                <span className="text-xs text-slate-600 dark:text-slate-300">{x.description}</span>
                {!x.enabled && <Chip cls="bg-rose-100 text-rose-800">غیرفعال</Chip>}
                {x.downtime !== 'none' && <Chip>{x.downtime === 'brief' ? 'قطعی کوتاه' : 'قطعی'}</Chip>}
              </li>
            ))}
          </ul>
        </Card>
      ))}
    </div>
  )
}

export function IncidentsPanel({ sessionId, onOpenChat }: { sessionId: string; onOpenChat: () => void }) {
  const [items, setItems] = useState<Incident[]>([])
  const [selected, setSelected] = useState<Incident | null>(null)
  const [patch, setPatch] = useState<any>(null)
  const [verify, setVerify] = useState<any>(null)
  const [busy, setBusy] = useState('')
  const reload = () => api.incidents().then((l) => { setItems(l); if (selected) setSelected(l.find((i) => i.id === selected.id) ?? null) }).catch(() => undefined)
  useEffect(() => {
    api.incidents().then(setItems).catch(() => undefined)
  }, [])
  const run = async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key)
    try {
      await fn()
    } finally {
      setBusy('')
      reload()
    }
  }
  const STATUS: Record<string, string> = { open: 'باز', investigated: 'بررسی‌شده', resolved: 'رفع‌شده', closed: 'بسته' }
  return (
    <div className="grid gap-3 md:grid-cols-[260px_1fr]">
      <Card title="رخدادها" icon="🚨">
        <ul className="space-y-1">
          {items.map((i) => (
            <li key={i.id}>
              <button onClick={() => { setSelected(i); setPatch(null); setVerify(null) }} className={`w-full rounded-xl px-2 py-1.5 text-right text-sm ${selected?.id === i.id ? 'bg-slate-100 dark:bg-slate-800' : 'hover:bg-slate-50 dark:hover:bg-slate-800/50'}`}>
                <div className="flex items-center justify-between"><span className="mono">{i.app_name}</span><Chip cls={i.status === 'closed' || i.status === 'resolved' ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'}>{STATUS[i.status] ?? i.status}</Chip></div>
                <div className="text-xs text-slate-500">{time(i.opened_at)} · {i.trigger}</div>
              </button>
            </li>
          ))}
          {!items.length && <li className="text-sm text-slate-500">رخدادی ثبت نشده.</li>}
        </ul>
      </Card>
      <div className="space-y-3">
        {!selected && <div className="card text-sm text-slate-500">یک رخداد را انتخاب کنید.</div>}
        {selected && (
          <>
            <Card title={`رخداد ${selected.app_name}`} icon="🧾">
              <div className="text-sm">{selected.summary ?? '—'}</div>
              <div className="mt-2 flex flex-wrap gap-2">
                <button className="btn-ghost text-xs" disabled={!!busy} onClick={() => run('verify', async () => setVerify(await api.verifyIncident(selected.id)))}>{busy === 'verify' ? 'در حال بررسی…' : '🔁 بررسی مجدد علائم'}</button>
                <button className="btn-ghost text-xs" disabled={!!busy} onClick={() => run('brief', async () => { const b = await api.fixBrief(selected.id); setSelected({ ...selected, fix_brief: b }) })}>📝 ساخت FixBrief</button>
                <button className="btn-ghost text-xs" disabled={!!busy} onClick={() => run('agent', async () => setPatch(await api.runCodingAgent(selected.id, '/home/user/Liara/demo/shop-demo', true)))}>{busy === 'agent' ? 'در حال اجرا…' : '🧩 اجرای ایجنت کدنویسی (demo patch)'}</button>
                {selected.status !== 'closed' && <button className="btn-ghost text-xs" disabled={!!busy} onClick={() => run('close', () => api.closeIncident(selected.id))}>✅ بستن رخداد</button>}
              </div>
            </Card>
            {selected.evidence && <EvidenceCard p={selected.evidence} />}
            {selected.hypotheses && <HypothesesCard p={{ items: selected.hypotheses, summary: '' }} />}
            {selected.remediation && (
              <>
                <RemediationCard p={{ ...selected.remediation, incident_id: selected.id }} sessionId={sessionId || selected.session_id || ''} />
                <button className="btn-ghost text-xs" onClick={onOpenChat}>↩ رفتن به گفتگو برای تأیید</button>
              </>
            )}
            {selected.fix_brief && (
              <Card title="FixBrief" icon="📝">
                <pre className="mono max-h-72 overflow-auto rounded-lg bg-slate-950 p-2 text-[11px] text-slate-100">{JSON.stringify(selected.fix_brief, null, 2)}</pre>
              </Card>
            )}
            {patch && <PatchCard p={patch} />}
            {verify && <VerificationCard p={verify} />}
          </>
        )}
      </div>
    </div>
  )
}
