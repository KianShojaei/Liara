import { useState } from 'react'
import { api } from '../api'
import { RISK, DOWNTIME, REVERSIBILITY, mb, num, signed, time } from '../format'
import type { Finding, Hypothesis, RemediationOption } from '../types'
import { Card, Chip, LineChart } from './ui'

const SEV: Record<string, string> = {
  critical: 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-200',
  warning: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200',
  info: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200',
}
const SEV_LABEL: Record<string, string> = { critical: 'بحرانی', warning: 'هشدار', info: 'اطلاع' }

export function IncidentBanner({ p }: { p: Record<string, any> }) {
  const closed = p.status === 'closed'
  return (
    <div className={`rounded-xl border px-3 py-2 text-sm ${closed ? 'border-emerald-300 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-900/20' : 'border-rose-300 bg-rose-50 dark:border-rose-800 dark:bg-rose-900/20'}`}>
      <b>{closed ? '✅ رخداد بسته شد' : '🚨 رخداد باز شد'}</b> — برنامه <span className="mono">{p.app}</span>
      {p.reasons?.length > 0 && <span> · {p.reasons.join('؛ ')}</span>}
      {p.summary && closed && <div className="mt-1 text-xs">{p.summary}</div>}
      <div className="mono mt-0.5 text-[10px] text-slate-500">{p.id}</div>
    </div>
  )
}

export function EvidenceCard({ p }: { p: Record<string, any> }) {
  const [open, setOpen] = useState(false)
  const findings: Finding[] = p.findings ?? []
  const series = p.series ?? {}
  return (
    <Card title="شواهد" icon="📊">
      <LineChart
        series={[
          { label: 'حافظه (MB)', points: series.memory ?? [], color: '#6366f1', unit: (v) => String(Math.round(v / 1024 / 1024)) },
          { label: 'CPU (هسته)', points: series.cpu ?? [], color: '#f59e0b', unit: (v) => v.toFixed(2) },
        ]}
      />
      <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
        {p.plan && <Chip>پلن {p.plan.id}: {num(p.plan.ram_gb, 2)}GB / {num(p.plan.cpu_cores, 1)} CPU</Chip>}
        {p.probe && <Chip cls={(p.probe.success_rate ?? 1) >= 0.67 ? SEV.info : SEV.critical}>پاسخ مستقیم: {Math.round((p.probe.success_rate ?? 0) * 100)}٪ موفق · {num(p.probe.p50_ms, 0)}ms</Chip>}
        {p.log_stats && <Chip>لاگ: {p.log_stats.total} خط، {p.log_stats.stderr} خطا</Chip>}
        {(p.applets ?? []).map((a: any) => (
          <Chip key={a.name} cls={/running|ready/i.test(a.state) ? SEV.info : SEV.critical}>
            {a.name}: {a.state} {a.reason}
          </Chip>
        ))}
      </div>
      {findings.length ? (
        <ul className="mt-3 space-y-1.5">
          {findings.map((f) => (
            <li key={f.kind} className="text-sm">
              <Chip cls={SEV[f.severity]}>{SEV_LABEL[f.severity]}</Chip> <span className="mr-1">{f.title}</span>
              <span className="text-xs text-slate-500">(اطمینان {Math.round(f.confidence * 100)}٪)</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm text-emerald-700">نشانه‌ی غیرعادی پیدا نشد.</p>
      )}
      {(p.error_samples?.length > 0 || p.events?.length > 0) && (
        <button className="mt-2 text-xs text-slate-500 underline" onClick={() => setOpen(!open)}>
          {open ? 'بستن جزئیات' : 'نمونه لاگ‌ها و رویدادها'}
        </button>
      )}
      {open && (
        <div className="mt-2 space-y-2">
          {p.error_samples?.length > 0 && (
            <pre className="mono max-h-48 overflow-auto rounded-lg bg-slate-950 p-2 text-[11px] text-rose-200">{p.error_samples.map((e: any) => `${e.ts}  ${e.message}`).join('\n')}</pre>
          )}
          {p.events?.length > 0 && (
            <ul className="text-xs text-slate-600 dark:text-slate-300">
              {p.events.slice(-8).map((e: any, i: number) => (
                <li key={i}>
                  <span className="mono">{time(e.ts)}</span> {e.text}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Card>
  )
}

export function HypothesesCard({ p }: { p: Record<string, any> }) {
  const items: Hypothesis[] = p.items ?? []
  return (
    <Card title="علت‌های احتمالی" icon="🧠">
      {p.summary && <p className="mb-2 text-sm leading-6">{p.summary}</p>}
      <ol className="space-y-3">
        {items.map((h, i) => (
          <li key={h.id} className="text-sm">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium">
                {i + 1}. {h.cause}
              </span>
              <span className="mono shrink-0 text-xs">{Math.round(h.confidence * 100)}٪</span>
            </div>
            <div className="mt-1 h-1.5 w-full rounded-full bg-slate-200 dark:bg-slate-800">
              <div className="h-1.5 rounded-full bg-indigo-500" style={{ width: `${Math.round(h.confidence * 100)}%` }} />
            </div>
            {h.explanation && <div className="mt-1 text-xs text-slate-600 dark:text-slate-300">شواهد: {h.explanation}</div>}
            {h.counter_evidence && <div className="mt-0.5 text-xs text-slate-500">چه چیزی نظرم را عوض می‌کند: {h.counter_evidence}</div>}
          </li>
        ))}
      </ol>
      {!items.length && <p className="text-sm text-slate-500">فرضیه‌ای وجود ندارد.</p>}
    </Card>
  )
}

export function RemediationCard({ p, sessionId }: { p: Record<string, any>; sessionId: string }) {
  const options: RemediationOption[] = p.options ?? []
  const [busy, setBusy] = useState('')
  const [done, setDone] = useState<Record<string, string>>({})
  if (!options.length) return null
  const pick = async (o: RemediationOption) => {
    setBusy(o.id)
    try {
      if (o.tool === 'submit_fix') {
        await api.runCodingAgent(p.incident_id, o.args.path ?? '', true)
        setDone((d) => ({ ...d, [o.id]: 'FixBrief ساخته شد؛ پچ و کارت تأیید در گفتگو می‌آید.' }))
      } else {
        const res = await api.remediate(p.incident_id, o.id, sessionId)
        setDone((d) => ({ ...d, [o.id]: res.decision?.mode === 'blocked' ? 'مسدود شد: ' + (res.decision.reasons ?? []).join('؛ ') : 'کارت تأیید ساخته شد.' }))
      }
    } catch (e) {
      setDone((d) => ({ ...d, [o.id]: 'خطا: ' + String((e as Error).message) }))
    } finally {
      setBusy('')
    }
  }
  return (
    <Card title="راه‌حل‌های پیشنهادی" icon="🛠️">
      <p className="mb-2 text-xs text-slate-500">هیچ‌کدام خودکار اجرا نمی‌شود؛ با انتخاب هر گزینه یک کارت تأیید ساخته می‌شود.</p>
      <div className="space-y-2">
        {options.map((o) => (
          <div key={o.id} className={`rounded-xl border p-2 text-sm ${o.recommended ? 'border-emerald-500 bg-emerald-50 dark:bg-emerald-900/20' : 'border-slate-200 dark:border-slate-800'}`}>
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="font-medium">{o.title}</span>
              {o.recommended && <Chip cls="bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200">پیشنهاد ما</Chip>}
              <Chip cls={o.risk === 'low' ? SEV.info : o.risk === 'medium' ? SEV.warning : SEV.critical}>{RISK[o.risk] ?? o.risk}</Chip>
              <Chip>{o.cost_delta_hourly ? `${signed(o.cost_delta_hourly)} تومان/ساعت` : 'بدون هزینه'}</Chip>
              <Chip>{REVERSIBILITY[o.reversibility] ?? o.reversibility}</Chip>
              <Chip>{DOWNTIME[o.downtime] ?? o.downtime}</Chip>
            </div>
            <div className="mt-1 text-xs text-slate-600 dark:text-slate-300">{o.rationale}</div>
            {o.requires && <div className="mt-0.5 text-xs text-slate-500">نیازمند: {o.requires}</div>}
            <div className="mt-2 flex items-center gap-2">
              <button className="btn-ghost text-xs" disabled={!!busy || !!done[o.id]} title="یک کارت تأیید ساخته می‌شود؛ تا تأیید نکنید چیزی اجرا نمی‌شود" onClick={() => pick(o)}>
                {busy === o.id ? 'در حال ساخت کارت…' : 'اجرای این راه‌حل'}
              </button>
              {done[o.id] && <span className="text-xs text-slate-500">{done[o.id]}</span>}
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}

export function VerificationCard({ p }: { p: Record<string, any> }) {
  const ok = !!p.ok
  const steps: { name: string; ok: boolean; detail: string }[] = p.steps ?? []
  return (
    <Card title={ok ? 'بررسی نتیجه: موفق' : 'بررسی نتیجه: ناموفق'} icon={ok ? '✅' : '⚠️'} tone={ok ? 'success' : 'error'}>
      {p.summary && <p className="text-sm">{p.summary}</p>}
      {steps.length > 0 && (
        <ul className="mt-1 space-y-0.5 text-sm">
          {steps.map((s, i) => (
            <li key={i}>
              <span className={s.ok ? 'text-emerald-600' : 'text-rose-600'}>{s.ok ? '✓' : '✗'}</span> <CheckName name={s.name} />: {s.detail}
            </li>
          ))}
        </ul>
      )}
      {p.comparison && (
        <div className="mt-2 grid grid-cols-2 gap-1 text-xs">
          <div>پاسخ موفق قبل/بعد: {pct(p.comparison.probe_success_before)} → {pct(p.comparison.probe_success_after)}</div>
          <div>حافظه قبل/بعد: {mb(p.comparison.memory_before)} → {mb(p.comparison.memory_after)}</div>
          <div className="col-span-2">یافته‌های بحرانی قبل: {(p.comparison.critical_before ?? []).join(', ') || '—'} · بعد: {(p.comparison.critical_after ?? []).join(', ') || '—'}</div>
        </div>
      )}
      {p.url && (
        <a className="mt-1 block text-sm text-emerald-700 underline" href={p.url} target="_blank" rel="noreferrer">
          {p.url}
        </a>
      )}
    </Card>
  )
}

function CheckName({ name }: { name: string }) {
  const map: Record<string, string> = { release: 'انتشار', container: 'کانتینر', http: 'پاسخ HTTP', logs: 'لاگ‌ها', app_exists: 'برنامه', plan: 'پلن', scale: 'روشن/خاموش', dns: 'DNS', ssl: 'SSL', https: 'HTTPS' }
  return <span>{map[name] ?? name}</span>
}

const pct = (v: number | null | undefined) => (v == null ? '—' : `${Math.round(v * 100)}٪`)

export function PatchCard({ p }: { p: Record<string, any> }) {
  return (
    <Card title={p.ok ? 'پچ پیشنهادی ایجنت کدنویسی' : 'ایجنت کدنویسی پچی نداد'} icon="🧩" tone={p.ok ? 'info' : 'warning'}>
      <div className="text-xs text-slate-500">شاخه: <span className="mono">{p.branch}</span> {p.log && `· ${p.log}`}</div>
      {p.patch && <pre className="mono mt-2 max-h-72 overflow-auto rounded-lg bg-slate-950 p-2 text-[11px] leading-5 text-slate-100">{p.patch.split('\n').map((l: string, i: number) => (
        <div key={i} className={l.startsWith('+') && !l.startsWith('+++') ? 'text-emerald-300' : l.startsWith('-') && !l.startsWith('---') ? 'text-rose-300' : ''}>{l}</div>
      ))}</pre>}
      {p.proposal_id && <div className="mt-2 text-xs">کارت تأیید برای اعمال این پچ و دیپلوی در ادامه آمده است.</div>}
    </Card>
  )
}

export function FixBriefCard({ p }: { p: Record<string, any> }) {
  return (
    <Card title="FixBrief برای ایجنت کدنویسی" icon="📝">
      <div className="text-sm">علامت: {p.symptom}</div>
      <div className="text-sm">علت مشکوک: {p.suspected_cause} ({Math.round((p.confidence ?? 0) * 100)}٪)</div>
      {p.suspected_files?.length > 0 && <div className="mono mt-1 text-xs">{p.suspected_files.join(', ')}</div>}
      <div className="mt-1 text-xs text-slate-600 dark:text-slate-300" dir="ltr">{p.fix_direction}</div>
      {p.path && <div className="mono mt-1 text-[10px] text-slate-500">{p.path}</div>}
    </Card>
  )
}

export function LogsCard({ p }: { p: Record<string, any> }) {
  const lines: { type: string; datetime: string; message: string }[] = p.lines ?? []
  return (
    <Card title={`لاگ‌های ${p.app}`} icon="📜">
      <pre className="mono max-h-64 overflow-auto rounded-lg bg-slate-950 p-2 text-[11px] leading-5 text-slate-100">
        {lines.map((l, i) => (
          <div key={i} className={l.type === 'stderr' ? 'text-rose-300' : ''}>
            {time(l.datetime)}  {l.message}
          </div>
        ))}
      </pre>
    </Card>
  )
}

export async function runVerify(id: string) {
  return api.verifyIncident(id)
}
