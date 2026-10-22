import { useState } from 'react'
import { api } from '../api'
import { num, toman } from '../format'
import { Card, Chip } from './ui'

const PLATFORM: Record<string, string> = { node: 'Node.js', next: 'Next.js', react: 'React (استاتیک)', vue: 'Vue', angular: 'Angular', django: 'Django', flask: 'Flask', python: 'Python', laravel: 'Laravel', php: 'PHP', dotnet: '.NET', go: 'Go', docker: 'Docker', static: 'سایت استاتیک', wordpress: 'WordPress' }

export function AnalysisCard({ p }: { p: Record<string, any> }) {
  return (
    <Card title="نتیجه‌ی بررسی پروژه" icon="🔍" tone="info">
      <p className="text-sm leading-6">{p.explanation}</p>
      <div className="mt-2 flex flex-wrap gap-1.5 text-xs">
        <Chip>پلتفرم: {PLATFORM[p.platform] ?? p.platform}</Chip>
        <Chip>پورت: {p.port}</Chip>
        <Chip>مسیر سلامت: <span className="mono">{p.health_path}</span></Chip>
        {(p.databases ?? []).map((d: string) => (
          <Chip key={d}>دیتابیس: {d}</Chip>
        ))}
        {(p.env_keys ?? []).length > 0 && <Chip>{p.env_keys.length} متغیر محیطی</Chip>}
      </div>
      {(p.warnings ?? []).length > 0 && (
        <ul className="mt-2 list-disc pr-5 text-xs text-amber-700 dark:text-amber-300">
          {p.warnings.map((w: string) => (
            <li key={w}>{w}</li>
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
  return (
    <Card title={`انتخاب پلن برای ${p.app_name}`} icon="💳" tone={p.balance_ok ? 'default' : 'warning'}>
      <div className="mb-2 text-sm">
        موجودی: <b>{toman(p.balance)}</b> — {p.balance_message}
        {p.app_exists && <span className="mr-2 text-xs text-slate-500">(برنامه از قبل وجود دارد؛ پلن فعلی حفظ می‌شود)</span>}
      </div>
      <div className="space-y-1.5">
        {p.options.map((o: any) => (
          <label key={o.plan_id} className={`flex cursor-pointer items-start gap-2 rounded-xl border p-2 text-sm ${chosen === o.plan_id ? 'border-emerald-500 bg-emerald-50 dark:bg-emerald-900/20' : 'border-slate-200 dark:border-slate-800'}`}>
            <input type="radio" name={`plan-${p.app_name}`} className="mt-1" checked={chosen === o.plan_id} disabled={saving} onChange={() => choose(o.plan_id)} />
            <div className="flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="mono font-semibold">{o.plan_id}</span>
                {o.recommended && <Chip cls="bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200">پیشنهاد ما</Chip>}
                <span className="text-xs text-slate-500">{num(o.ram_gb, 2)} GB RAM · {num(o.cpu_cores, 1)} CPU · {num(o.disk_gb, 0)} GB دیسک</span>
              </div>
              <div className="text-xs">
                {o.hourly_price ? `${toman(o.hourly_price)} در ساعت (${toman(o.monthly_price)} در ماه)` : 'رایگان'} · با موجودی فعلی: {o.runway_label}
              </div>
              {o.reasons?.length > 0 && <div className="mt-0.5 text-xs text-slate-500">{o.reasons.join(' · ')}</div>}
            </div>
          </label>
        ))}
      </div>
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
    <Card title="متغیرهای محیطی" icon="🔐">
      <p className="text-sm leading-6">{p.text}</p>
      <div className="mt-2 space-y-2">
        {(p.keys as string[]).map((k) => (
          <label key={k} className="flex items-center gap-2 text-sm">
            <span className="mono w-40 shrink-0 text-xs">{k}</span>
            <input className="input" disabled={done} type={(p.secret_keys as string[]).includes(k) ? 'password' : 'text'} value={values[k]} onChange={(e) => setValues({ ...values, [k]: e.target.value })} placeholder="خالی = تنظیم نشود" />
          </label>
        ))}
      </div>
      {!done ? (
        <button className="btn-primary mt-3" disabled={busy} onClick={submit}>
          ادامه
        </button>
      ) : (
        <div className="mt-2 text-xs text-emerald-700">ثبت شد؛ کارت تأیید در ادامه می‌آید.</div>
      )}
    </Card>
  )
}

export function ManualStepCard({ p, sessionId, app }: { p: Record<string, any>; sessionId: string; app?: string }) {
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)
  const confirm = async () => {
    setBusy(true)
    try {
      await api.manualStepDone(sessionId, p.id, { app, zone: p.zone, domain_id: p.domain_id })
      setDone(true)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Card title={`کار دستی: ${p.title}`} icon="🖐️" tone="warning">
      <p className="text-sm leading-6">{p.summary}</p>
      {p.reason && <p className="mt-1 text-sm text-amber-700 dark:text-amber-300">{p.reason}</p>}
      {p.records && (
        <div className="mono mt-2 rounded-lg bg-slate-100 p-2 text-xs dark:bg-slate-950">
          {Object.entries(p.records).map(([k, v]) => (
            <div key={k}>
              {k}: {String(v)}
            </div>
          ))}
        </div>
      )}
      <ol className="mt-2 list-decimal space-y-1 pr-5 text-sm">
        {(p.manual_steps ?? []).map((s: string) => (
          <li key={s}>{s}</li>
        ))}
      </ol>
      <div className="mt-3 flex flex-wrap gap-2">
        {p.console_url && (
          <a className="btn-ghost" href={p.console_url} target="_blank" rel="noreferrer">
            باز کردن کنسول لیارا ↗
          </a>
        )}
        <button className="btn-primary" disabled={busy || done} onClick={confirm}>
          {done ? '✓ بررسی شد' : 'انجام شد، دوباره بررسی کن'}
        </button>
      </div>
    </Card>
  )
}
