import { useEffect, useState } from 'react'
import { api } from '../api'
import { ACTION, ACTOR, PROPOSAL_STATUS, TIER, dateTime, time } from '../format'
import type { AuditRow, Incident, Limitation, PolicyTool } from '../types'
import { EvidenceCard, FixBriefCard, HypothesesCard, PatchCard, RemediationCard, VerificationCard } from './IncidentCards'
import { Button, Card, Chip, Empty, Ltr, Skeleton } from './ui'

export function AuditPanel() {
  const [rows, setRows] = useState<AuditRow[] | null>(null)
  useEffect(() => {
    api.audit(200).then(setRows).catch(() => setRows([]))
  }, [])
  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div>
        <h2 className="text-base font-semibold">دفتر ثبت وقایع</h2>
        <p className="text-sm text-muted">هر پیشنهاد، تأیید، اجرا و بررسی اینجا ثبت می‌شود و قابل حذف نیست (append-only).</p>
      </div>
      <Card>
        {rows == null && <Skeleton className="h-24" />}
        {rows && rows.length === 0 && <Empty icon="📒" title="هنوز چیزی ثبت نشده" hint="اولین عملیات را از گفتگو شروع کنید." />}
        {rows && rows.length > 0 && (
          <div className="-mx-4 overflow-x-auto sm:-mx-5">
            <table className="w-full min-w-[40rem] text-xs">
              <thead className="text-muted">
                <tr className="border-b border-line">
                  <th className="px-4 py-2 text-right font-medium sm:px-5">زمان</th>
                  <th className="py-2 text-right font-medium">چه کسی</th>
                  <th className="py-2 text-right font-medium">کار</th>
                  <th className="py-2 text-right font-medium">ابزار</th>
                  <th className="py-2 text-right font-medium">سطح</th>
                  <th className="px-4 py-2 text-right font-medium sm:px-5">نتیجه</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-t border-line/60 hover:bg-raised/40">
                    <td className="px-4 py-1.5 text-muted sm:px-5">{dateTime(r.ts)}</td>
                    <td className="py-1.5">{ACTOR[r.actor] ?? r.actor}</td>
                    <td className="py-1.5">{ACTION[r.action] ?? r.action}</td>
                    <td className="py-1.5"><Ltr>{r.tool ?? ''}</Ltr></td>
                    <td className="py-1.5">{r.tier && <Chip tone={TIER[r.tier]?.tone ?? 'neutral'}>{r.tier}</Chip>}</td>
                    <td className="px-4 py-1.5 sm:px-5"><Chip tone={PROPOSAL_STATUS[r.outcome]?.tone ?? 'neutral'}>{PROPOSAL_STATUS[r.outcome]?.label ?? r.outcome}</Chip></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}

export function LimitationsPanel() {
  const [items, setItems] = useState<Limitation[] | null>(null)
  useEffect(() => {
    api.limitations().then(setItems).catch(() => setItems([]))
  }, [])
  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div>
        <h2 className="text-base font-semibold">محدودیت‌های API لیارا</h2>
        <p className="text-sm text-muted">این کارها از طریق API ممکن نیست؛ دستیار برای هرکدام یک کارت «کار دستی» با مراحل دقیق نشان می‌دهد و بعد از «انجام شد» دوباره بررسی می‌کند.</p>
      </div>
      {items == null && <Skeleton className="h-24" />}
      <div className="grid gap-3 md:grid-cols-2">
        {items?.map((l) => (
          <Card key={l.id} title={l.title} icon="🖐️" meta={l.verify_tool ? <Chip tone="success">بررسی خودکار بعد از انجام</Chip> : undefined}>
            <p className="text-sm">{l.summary}</p>
            {l.manual_steps && (
              <ol className="mt-3 space-y-1.5 text-sm">
                {l.manual_steps.map((s, i) => (
                  <li key={s} className="flex gap-2">
                    <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-raised text-[11px] font-semibold text-muted">{i + 1}</span>
                    <span>{s}</span>
                  </li>
                ))}
              </ol>
            )}
            {l.console_url && (
              <a className="btn-ghost btn-sm mt-3" href={l.console_url} target="_blank" rel="noreferrer">
                کنسول لیارا ↗
              </a>
            )}
          </Card>
        ))}
      </div>
    </div>
  )
}

export function PolicyPanel() {
  const [tools, setTools] = useState<PolicyTool[] | null>(null)
  useEffect(() => {
    api.policyTools().then(setTools).catch(() => setTools([]))
  }, [])
  const DESC: Record<string, string> = {
    T0: 'فقط خواندن؛ خودکار اجرا می‌شود.',
    T1: 'تغییر کم‌ریسک؛ خودکار با اطلاع‌رسانی.',
    T2: 'تغییر وضعیت؛ فقط با تأیید شما، سپس اجرا و بررسی.',
    T3: 'محافظت‌شده (حذف، غیرفعال کردن SSL، کاهش پلن)؛ به‌صورت پیش‌فرض خاموش و نیازمند تایپ تأیید.',
  }
  const DT: Record<string, string> = { brief: 'قطعی کوتاه', yes: 'قطعی' }
  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div>
        <h2 className="text-base font-semibold">سطوح ریسک عملیات</h2>
        <p className="text-sm text-muted">هر ابزار با سطح ریسک ثبت شده است؛ مدل هیچ‌وقت نمی‌تواند تغییر سطح T2 یا بالاتر را بدون تأیید انسانی اجرا کند.</p>
      </div>
      {tools == null && <Skeleton className="h-24" />}
      {(['T0', 'T1', 'T2', 'T3'] as const).map((t) => (
        <Card key={t} title={`${t} — ${TIER[t].label}`} icon="🛡️" meta={<Chip tone={TIER[t].tone}>{tools?.filter((x) => x.tier === t).length ?? 0} ابزار</Chip>}>
          <p className="mb-3 text-xs text-muted">{DESC[t]}</p>
          <ul className="divide-y divide-line">
            {tools?.filter((x) => x.tier === t).map((x) => (
              <li key={x.name} className="flex flex-wrap items-center gap-2 py-1.5 text-sm">
                <Ltr className="w-40 shrink-0 text-xs font-medium">{x.name}</Ltr>
                <span className="flex-1 text-xs text-muted">{x.description}</span>
                {!x.enabled && <Chip tone="danger">غیرفعال</Chip>}
                {x.downtime !== 'none' && <Chip tone="outline">{DT[x.downtime] ?? x.downtime}</Chip>}
              </li>
            ))}
          </ul>
        </Card>
      ))}
    </div>
  )
}

export function IncidentsPanel({ sessionId, onOpenChat }: { sessionId: string; onOpenChat: () => void }) {
  const [items, setItems] = useState<Incident[] | null>(null)
  const [selected, setSelected] = useState<Incident | null>(null)
  const [patch, setPatch] = useState<any>(null)
  const [verify, setVerify] = useState<any>(null)
  const [busy, setBusy] = useState('')
  const reload = () =>
    api
      .incidents()
      .then((l) => {
        setItems(l)
        if (selected) setSelected(l.find((i) => i.id === selected.id) ?? null)
      })
      .catch(() => setItems([]))
  useEffect(() => {
    api.incidents().then((l) => { setItems(l); if (!selected && l.length) setSelected(l[0]) }).catch(() => setItems([]))
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
  const STATUS: Record<string, { label: string; tone: 'success' | 'danger' | 'warning' | 'neutral' }> = { open: { label: 'باز', tone: 'danger' }, investigated: { label: 'بررسی‌شده', tone: 'warning' }, resolved: { label: 'رفع‌شده', tone: 'success' }, closed: { label: 'بسته', tone: 'neutral' } }
  return (
    <div className="grid gap-4 lg:grid-cols-[17rem_1fr]">
      <div className="space-y-2">
        <h2 className="text-base font-semibold">رخدادها</h2>
        {items == null && <Skeleton className="h-16" />}
        {items && items.length === 0 && <Empty icon="🚨" title="رخدادی ثبت نشده" hint="وقتی پایشگر مشکلی ببیند یا شما بگویید «سایت کند شده»، اینجا ثبت می‌شود." />}
        <ul className="space-y-1.5">
          {items?.map((i) => (
            <li key={i.id}>
              <button onClick={() => { setSelected(i); setPatch(null); setVerify(null) }} className={`w-full rounded-xl border px-3 py-2 text-right text-sm transition-colors ${selected?.id === i.id ? 'border-emerald-500/60 bg-emerald-500/10' : 'border-line hover:bg-raised/50'}`}>
                <div className="flex items-center justify-between gap-2">
                  <Ltr className="font-medium">{i.app_name}</Ltr>
                  <Chip tone={STATUS[i.status]?.tone ?? 'neutral'}>{STATUS[i.status]?.label ?? i.status}</Chip>
                </div>
                <div className="mt-0.5 truncate text-xs text-muted">{time(i.opened_at)} · {i.trigger}</div>
              </button>
            </li>
          ))}
        </ul>
      </div>
      <div className="min-w-0 space-y-3">
        {!selected && items && items.length > 0 && <Empty icon="👈" title="یک رخداد را انتخاب کنید" />}
        {selected && (
          <>
            <Card title={<span>رخداد <Ltr>{selected.app_name}</Ltr></span>} icon="🧾" meta={<Chip tone={STATUS[selected.status]?.tone ?? 'neutral'}>{STATUS[selected.status]?.label ?? selected.status}</Chip>}>
              <div className="text-sm">{selected.summary ?? '—'}</div>
              <div className="mt-1 text-xs text-muted">{dateTime(selected.opened_at)} · {selected.trigger}</div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button size="sm" loading={busy === 'verify'} disabled={!!busy} onClick={() => run('verify', async () => setVerify(await api.verifyIncident(selected.id)))}>🔁 بررسی مجدد علائم</Button>
                <Button size="sm" loading={busy === 'brief'} disabled={!!busy} onClick={() => run('brief', async () => { const b = await api.fixBrief(selected.id); setSelected({ ...selected, fix_brief: b }) })}>📝 ساخت FixBrief</Button>
                <Button size="sm" loading={busy === 'agent'} disabled={!!busy} onClick={() => run('agent', async () => { const projects = await api.projects().catch(() => []); const match = projects.find((p) => p.name === selected.app_name) ?? projects[0]; setPatch(await api.runCodingAgent(selected.id, match?.path ?? '', true)) })}>🧩 اجرای ایجنت کدنویسی (demo)</Button>
                {selected.status !== 'closed' && <Button size="sm" variant="ghost" disabled={!!busy} onClick={() => run('close', () => api.closeIncident(selected.id))}>✅ بستن رخداد</Button>}
              </div>
            </Card>
            {selected.evidence && <EvidenceCard p={selected.evidence} />}
            {selected.hypotheses && <HypothesesCard p={{ items: selected.hypotheses, summary: '' }} />}
            {selected.remediation && (
              <>
                <RemediationCard p={{ ...selected.remediation, incident_id: selected.id }} sessionId={sessionId || selected.session_id || ''} />
                <Button variant="ghost" size="sm" onClick={onOpenChat}>↩ رفتن به گفتگو برای تأیید</Button>
              </>
            )}
            {selected.fix_brief && <FixBriefCard p={selected.fix_brief} />}
            {patch && <PatchCard p={patch} />}
            {verify && <VerificationCard p={verify} />}
          </>
        )}
      </div>
    </div>
  )
}
