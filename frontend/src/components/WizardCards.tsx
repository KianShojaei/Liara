import { useState } from 'react'
import { api } from '../api'
import { PLATFORM, num, toman } from '../format'
import { Button, Card, Chip, Ltr } from './ui'

export function AnalysisCard({ p }: { p: Record<string, any> }) {
  return (
    <Card title="نتیجه‌ی بررسی پروژه" icon="🔍" tone="info">
      <p className="text-sm">{p.explanation}</p>
      <div className="mt-3 flex flex-wrap gap-1.5">
        <Chip tone="info">پلتفرم: {PLATFORM[p.platform] ?? p.platform}</Chip>
        <Chip>پورت: <Ltr>{p.port}</Ltr></Chip>
        <Chip>مسیر سلامت: <Ltr>{p.health_path}</Ltr></Chip>
        {(p.databases ?? []).map((d: string) => (
          <Chip key={d} tone="violet">دیتابیس: {d}</Chip>
        ))}
        {(p.env_keys ?? []).length > 0 && <Chip tone="warning">{p.env_keys.length} متغیر محیطی</Chip>}
      </div>
      {(p.warnings ?? []).length > 0 && (
        <ul className="mt-2 space-y-0.5 text-xs text-amber-400">
          {p.warnings.map((w: string) => (
            <li key={w}>⚠ {w}</li>
          ))}
        </ul>
      )}
    </Card>
  )
}

export function PlanOptionsCard({ p, sessionId }: { p: Record<string, any>; sessionId: string }) {
  const [chosen, setChosen] = useState<string>(p.recommended_plan_id)
  const [saving, setSaving] = useState(false)
  const choose = async (id: string) => {
    setChosen(id)
    setSaving(true)
    try {
      await api.wizardPlan(sessionId, id)
    } finally {
      setSaving(false)
    }
  }
  const options: any[] = p.options ?? []
  const fitting = options.filter((o) => !(o.reasons ?? []).some((r: string) => r.startsWith('RAM')))
  const [showAll, setShowAll] = useState(false)
  const list = showAll ? options : fitting.slice(0, 4)
  return (
    <Card title={`انتخاب پلن برای ${p.app_name}`} icon="💳" tone={p.balance_ok ? 'default' : 'warning'} meta={<Chip tone={p.low_balance || !p.balance_ok ? 'warning' : 'success'}>موجودی {toman(p.balance)}</Chip>}>
      <p className="text-sm text-muted">
        {p.balance_message}
        {p.app_exists && ' (برنامه از قبل وجود دارد؛ پلن فعلی حفظ می‌شود)'}
      </p>
      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {list.map((o: any) => (
          <label key={o.plan_id} className={`cursor-pointer rounded-xl border p-3 text-sm transition-colors ${chosen === o.plan_id ? 'border-emerald-500 bg-emerald-500/10 ring-1 ring-emerald-500/30' : 'border-line hover:border-emerald-500/40'}`}>
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-2">
                <input type="radio" name={`plan-${p.app_name}`} className="accent-emerald-500" checked={chosen === o.plan_id} disabled={saving} onChange={() => choose(o.plan_id)} />
                <Ltr className="font-semibold">{o.plan_id}</Ltr>
              </span>
              {o.recommended && <Chip tone="success">پیشنهاد ما</Chip>}
            </div>
            <div className="mt-1 text-xs text-muted">
              {num(o.ram_gb, 2)} GB RAM · {num(o.cpu_cores, 1)} CPU · {num(o.disk_gb, 0)} GB دیسک
            </div>
            <div className="mt-1 text-sm font-medium">{o.hourly_price ? `${toman(o.hourly_price)} / ساعت` : 'رایگان'}</div>
            <div className="text-xs text-muted">{o.hourly_price ? `${toman(o.monthly_price)} / ماه · ` : ''}کفاف موجودی: {o.runway_label}</div>
            {o.reasons?.length > 0 && <div className="mt-1 text-[11px] text-muted">{o.reasons.join(' · ')}</div>}
          </label>
        ))}
      </div>
      {options.length > list.length && (
        <Button variant="ghost" size="sm" className="mt-2" onClick={() => setShowAll(true)}>
          نمایش همه‌ی پلن‌ها ({options.length})
        </Button>
      )}
    </Card>
  )
}

export function EnvFormCard({ p, sessionId }: { p: Record<string, any>; sessionId: string }) {
  const [values, setValues] = useState<Record<string, string>>(() => Object.fromEntries((p.keys as string[]).map((k) => [k, ''])))
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)
  const submit = async () => {
    setBusy(true)
    try {
      await api.wizardEnv(sessionId, values)
      setDone(true)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Card title="متغیرهای محیطی" icon="🔐" meta={done ? <Chip tone="success">ثبت شد</Chip> : undefined}>
      <p className="text-sm text-muted">{p.text}</p>
      <div className="mt-3 space-y-2">
        {(p.keys as string[]).map((k) => (
          <label key={k} className="flex flex-col gap-1 text-sm sm:flex-row sm:items-center sm:gap-2">
            <Ltr className="w-44 shrink-0 text-xs">{k}</Ltr>
            <input className="input" dir="ltr" disabled={done} type={(p.secret_keys as string[]).includes(k) ? 'password' : 'text'} value={values[k]} onChange={(e) => setValues({ ...values, [k]: e.target.value })} placeholder="خالی = تنظیم نشود" />
          </label>
        ))}
      </div>
      {!done ? (
        <Button variant="primary" className="mt-3" loading={busy} onClick={submit}>
          ادامه
        </Button>
      ) : (
        <div className="mt-2 text-xs text-emerald-500">ثبت شد؛ کارت تأیید در ادامه می‌آید.</div>
      )}
    </Card>
  )
}

export function ManualStepCard({ p, sessionId, app }: { p: Record<string, any>; sessionId: string; app?: string }) {
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState<string | null>(null)
  const confirm = async () => {
    setBusy(true)
    try {
      await api.manualStepDone(sessionId, p.id, { app, zone: p.zone, domain_id: p.domain_id, ...(p.context ?? {}) })
      setDone(true)
    } finally {
      setBusy(false)
    }
  }
  const copy = async (key: string, value: string) => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(key)
      setTimeout(() => setCopied(null), 1500)
    } catch {
      /* clipboard unavailable */
    }
  }
  const records: { type: string; name: string; value: string; note?: string }[] = Array.isArray(p.records) ? p.records : []
  const legacyRecords = !Array.isArray(p.records) && p.records ? Object.entries(p.records as Record<string, unknown>) : []
  return (
    <Card title={p.title} icon="🖐️" tone="warning" meta={<Chip tone="warning">نیاز به کار دستی</Chip>}>
      <p className="text-sm">{p.summary}</p>
      {p.domain && <p className="mt-1 text-sm">دامنه: <Ltr className="font-medium">{p.domain}</Ltr></p>}
      {p.reason && <p className="mt-1 text-sm text-amber-400">{p.reason}</p>}
      {records.length > 0 && (
        <div className="mt-3 overflow-x-auto rounded-xl border border-line">
          <table className="w-full text-xs">
            <thead className="bg-raised/60 text-muted">
              <tr>
                <th className="px-3 py-1.5 text-right font-medium">نوع</th>
                <th className="px-3 py-1.5 text-right font-medium">نام</th>
                <th className="px-3 py-1.5 text-right font-medium">مقدار</th>
                <th className="px-3 py-1.5" />
              </tr>
            </thead>
            <tbody>
              {records.map((r, i) => (
                <tr key={i} className="border-t border-line">
                  <td className="px-3 py-1.5"><Chip tone="info">{r.type}</Chip></td>
                  <td className="px-3 py-1.5"><Ltr className="select-all">{r.name}</Ltr></td>
                  <td className="px-3 py-1.5">
                    <Ltr className="select-all break-all">{r.value}</Ltr>
                    {r.note && <div className="text-[11px] text-muted">{r.note}</div>}
                  </td>
                  <td className="px-2 py-1.5 text-left">
                    <Button size="sm" variant="ghost" onClick={() => copy(`${i}`, r.value)}>{copied === `${i}` ? '✓ کپی شد' : 'کپی'}</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {legacyRecords.length > 0 && (
        <div className="mt-2 rounded-xl border border-line bg-bg/60 p-3">
          {legacyRecords.map(([k, v]) => (
            <div key={k} className="flex flex-wrap gap-2 text-xs">
              <span className="text-muted">{k}</span>
              <Ltr className="select-all">{String(v)}</Ltr>
            </div>
          ))}
        </div>
      )}
      <ol className="mt-3 space-y-2 text-sm">
        {(p.manual_steps ?? []).map((s: string, i: number) => (
          <li key={s} className="flex gap-3">
            <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-amber-400/20 text-xs font-semibold text-amber-500">{i + 1}</span>
            <span>{s}</span>
          </li>
        ))}
      </ol>
      {p.extra && (
        <div className="mt-3 rounded-xl border border-line bg-bg/50 p-3 text-xs">
          <div className="font-medium">{p.extra.title}</div>
          <div className="mt-0.5 text-muted">{p.extra.summary}</div>
          {p.extra.manual_steps && (
            <ol className="mt-1 list-decimal space-y-0.5 pr-4 text-muted">
              {p.extra.manual_steps.map((s: string) => <li key={s}>{s}</li>)}
            </ol>
          )}
        </div>
      )}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button variant="primary" loading={busy} disabled={done} onClick={confirm}>
          {done ? '✓ بررسی شد' : 'انجام شد، دوباره بررسی کن'}
        </Button>
        {p.console_url && (
          <a className="btn-ghost" href={p.console_url} target="_blank" rel="noreferrer">
            باز کردن کنسول لیارا ↗
          </a>
        )}
      </div>
    </Card>
  )
}
