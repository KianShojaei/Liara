import { useState } from 'react'
import { api } from '../api'
import { CHECK_NAMES, DOWNTIME, REVERSIBILITY, RISK, RISK_TONE, checkDetail, mb, num, pct, signed, time } from '../format'
import type { Finding, Hypothesis, RemediationOption } from '../types'
import { Button, Card, Check, Chip, Expander, LineChart, Ltr } from './ui'

const SEV_TONE = { critical: 'danger', warning: 'warning', info: 'neutral' } as const
const SEV_LABEL: Record<string, string> = { critical: 'بحرانی', warning: 'هشدار', info: 'اطلاع' }

export function IncidentBanner({ p }: { p: Record<string, any> }) {
  const closed = p.status === 'closed'
  return (
    <div className={`flex items-start gap-3 rounded-2xl border px-4 py-3 text-sm ${closed ? 'border-emerald-500/40 bg-emerald-500/10' : 'border-rose-500/40 bg-rose-500/10'}`}>
      <span className="text-lg" aria-hidden>{closed ? '✅' : '🚨'}</span>
      <div className="min-w-0 flex-1">
        <div className="font-semibold">{closed ? 'رخداد بسته شد' : 'رخداد باز شد'} — <Ltr>{p.app}</Ltr></div>
        {p.reasons?.length > 0 && <div className="mt-0.5 text-xs text-muted">{p.reasons.join('؛ ')}</div>}
        {p.summary && closed && <div className="mt-1 text-xs">{p.summary}</div>}
      </div>
      <Ltr className="text-[10px] text-muted">{p.id}</Ltr>
    </div>
  )
}

export function EvidenceCard({ p }: { p: Record<string, any> }) {
  const findings: Finding[] = p.findings ?? []
  const series = p.series ?? {}
  const ramLimit = p.plan?.ram_gb ? p.plan.ram_gb * 1024 ** 3 : undefined
  const cpuLimit = p.plan?.cpu_cores
  return (
    <Card title="شواهد" icon="📊" meta={p.window_minutes ? <Chip tone="outline">{p.window_minutes} دقیقه‌ی اخیر</Chip> : undefined}>
      <LineChart
        series={[
          { label: 'حافظه (MB)', points: series.memory ?? [], color: '#818cf8', unit: (v) => String(Math.round(v / 1024 / 1024)), threshold: ramLimit, thresholdLabel: 'سقف پلن' },
          { label: 'CPU (هسته)', points: series.cpu ?? [], color: '#f59e0b', unit: (v) => v.toFixed(2), threshold: cpuLimit, thresholdLabel: 'سقف پلن' },
        ]}
      />
      <div className="mt-3 flex flex-wrap gap-1.5">
        {p.plan && <Chip>پلن <Ltr>{p.plan.id}</Ltr>: {num(p.plan.ram_gb, 2)}GB / {num(p.plan.cpu_cores, 1)} CPU</Chip>}
        {p.probe && <Chip tone={(p.probe.success_rate ?? 1) >= 0.67 ? 'success' : 'danger'}>پاسخ مستقیم: {pct(p.probe.success_rate)} موفق · {num(p.probe.p50_ms, 0)}ms</Chip>}
        {p.log_stats && <Chip>لاگ: {p.log_stats.total} خط، {p.log_stats.stderr} خطا</Chip>}
        {(p.applets ?? []).map((a: any) => (
          <Chip key={a.name} tone={/running|ready/i.test(a.state) ? 'success' : 'danger'}>
            <Ltr>{a.name}</Ltr>: {a.state} {a.reason}
          </Chip>
        ))}
      </div>
      {findings.length ? (
        <ul className="mt-3 divide-y divide-line">
          {findings.map((f) => (
            <li key={f.kind} className="flex flex-wrap items-center gap-2 py-2 text-sm">
              <Chip tone={SEV_TONE[f.severity]}>{SEV_LABEL[f.severity]}</Chip>
              <span className="flex-1">{f.title}</span>
              <span className="text-xs text-muted">اطمینان {pct(f.confidence)}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm text-emerald-500">نشانه‌ی غیرعادی پیدا نشد.</p>
      )}
      {(p.error_samples?.length > 0 || p.events?.length > 0) && (
        <Expander label="جزئیات: نمونه لاگ‌ها و رویدادها">
          <div className="space-y-2">
            {p.error_samples?.length > 0 && <pre className="code max-h-48 overflow-auto text-rose-200">{p.error_samples.map((e: any) => `${e.ts}  ${e.message}`).join('\n')}</pre>}
            {p.events?.length > 0 && (
              <ul className="space-y-0.5 text-xs text-muted">
                {p.events.slice(-8).map((e: any, i: number) => (
                  <li key={i}>
                    <Ltr>{time(e.ts)}</Ltr> {e.text}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Expander>
      )}
    </Card>
  )
}

export function HypothesesCard({ p }: { p: Record<string, any> }) {
  const items: Hypothesis[] = p.items ?? []
  return (
    <Card title="علت‌های احتمالی" icon="🧠">
      {p.summary && <p className="mb-3 text-sm">{p.summary}</p>}
      <ol className="space-y-4">
        {items.map((h, i) => {
          const c = Math.round(h.confidence * 100)
          const bar = c >= 70 ? 'bg-rose-500' : c >= 40 ? 'bg-amber-400' : 'bg-sky-400'
          return (
            <li key={h.id} className="text-sm">
              <div className="flex items-center justify-between gap-3">
                <span className="font-medium">
                  <span className="ml-1 text-muted">{i + 1}.</span>
                  {h.cause}
                </span>
                <span className="mono shrink-0 text-xs font-semibold">{c}٪</span>
              </div>
              <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-raised">
                <div className={`h-full rounded-full transition-all ${bar}`} style={{ width: `${c}%` }} />
              </div>
              {h.explanation && <div className="mt-1.5 text-xs text-muted"><span className="font-medium text-ink/80">شواهد:</span> {h.explanation}</div>}
              {h.counter_evidence && <div className="mt-0.5 text-xs text-muted"><span className="font-medium text-ink/80">چه چیزی نظرم را عوض می‌کند:</span> {h.counter_evidence}</div>}
            </li>
          )
        })}
      </ol>
      {!items.length && <p className="text-sm text-muted">فرضیه‌ای وجود ندارد.</p>}
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
      <p className="mb-3 text-xs text-muted">هیچ‌کدام خودکار اجرا نمی‌شود؛ با انتخاب هر گزینه یک کارت تأیید ساخته می‌شود.</p>
      <div className="grid gap-2">
        {options.map((o) => (
          <div key={o.id} className={`rounded-xl border p-3 text-sm ${o.recommended ? 'border-emerald-500/60 bg-emerald-500/10' : 'border-line'}`}>
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="font-medium">{o.title}</span>
              {o.recommended && <Chip tone="success">پیشنهاد ما</Chip>}
            </div>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              <Chip tone={RISK_TONE[o.risk] ?? 'neutral'}>{RISK[o.risk] ?? o.risk}</Chip>
              <Chip tone={o.cost_delta_hourly ? 'warning' : 'outline'}>{o.cost_delta_hourly ? `${signed(o.cost_delta_hourly)} تومان/ساعت` : 'بدون هزینه'}</Chip>
              <Chip tone="outline">{REVERSIBILITY[o.reversibility] ?? o.reversibility}</Chip>
              <Chip tone="outline">{DOWNTIME[o.downtime] ?? o.downtime}</Chip>
            </div>
            <div className="mt-2 text-xs text-muted">{o.rationale}</div>
            {o.requires && <div className="mt-0.5 text-xs text-muted">نیازمند: {o.requires}</div>}
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Button variant={o.recommended ? 'primary' : 'secondary'} size="sm" loading={busy === o.id} disabled={!!busy || !!done[o.id]} title="یک کارت تأیید ساخته می‌شود؛ تا تأیید نکنید چیزی اجرا نمی‌شود" onClick={() => pick(o)}>
                {done[o.id] ? '✓ ارسال شد' : 'اجرای این راه‌حل'}
              </Button>
              {done[o.id] && <span className="text-xs text-muted">{done[o.id]}</span>}
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
        <ul className="mt-2 grid gap-1 text-sm sm:grid-cols-2">
          {steps.map((s, i) => (
            <li key={i} className="flex items-center gap-2">
              <Check ok={s.ok} />
              <span className="font-medium">{CHECK_NAMES[s.name] ?? s.name}</span>
              <span className="text-xs text-muted">{checkDetail(s.detail)}</span>
            </li>
          ))}
        </ul>
      )}
      {p.comparison && (
        <dl className="mt-3 grid grid-cols-2 gap-2 text-xs">
          <Cmp label="پاسخ موفق" before={pct(p.comparison.probe_success_before)} after={pct(p.comparison.probe_success_after)} />
          <Cmp label="حافظه" before={mb(p.comparison.memory_before)} after={mb(p.comparison.memory_after)} />
          <Cmp label="یافته‌های بحرانی" before={(p.comparison.critical_before ?? []).join(', ') || '—'} after={(p.comparison.critical_after ?? []).join(', ') || '—'} wide />
        </dl>
      )}
      {p.url && (
        <a className="mt-2 block text-sm text-emerald-500 hover:underline" href={p.url} target="_blank" rel="noreferrer" dir="ltr">
          {p.url}
        </a>
      )}
    </Card>
  )
}

function Cmp({ label, before, after, wide }: { label: string; before: string; after: string; wide?: boolean }) {
  return (
    <div className={`rounded-xl border border-line bg-bg/50 px-3 py-2 ${wide ? 'col-span-2' : ''}`}>
      <dt className="text-[11px] text-muted">{label}</dt>
      <dd>
        <span className="text-muted">{before}</span> <span className="text-muted">←</span> <span className="font-medium">{after}</span>
      </dd>
    </div>
  )
}

export function PatchCard({ p }: { p: Record<string, any> }) {
  return (
    <Card title={p.ok ? 'پچ پیشنهادی ایجنت کدنویسی' : 'ایجنت کدنویسی پچی نداد'} icon="🧩" tone={p.ok ? 'info' : 'warning'} meta={p.branch ? <Chip tone="outline"><Ltr>{p.branch}</Ltr></Chip> : undefined}>
      {p.log && <div className="text-xs text-muted">{p.log}</div>}
      {p.patch && (
        <pre className="code mt-2 max-h-72 overflow-auto">
          {p.patch.split('\n').map((l: string, i: number) => (
            <div key={i} className={l.startsWith('+') && !l.startsWith('+++') ? 'bg-emerald-500/10 text-emerald-300' : l.startsWith('-') && !l.startsWith('---') ? 'bg-rose-500/10 text-rose-300' : l.startsWith('@@') ? 'text-sky-300' : ''}>
              {l}
            </div>
          ))}
        </pre>
      )}
      {p.proposal_id && <div className="mt-2 text-xs text-muted">کارت تأیید برای اعمال این پچ و دیپلوی در ادامه آمده است.</div>}
    </Card>
  )
}

export function FixBriefCard({ p }: { p: Record<string, any> }) {
  return (
    <Card title="FixBrief برای ایجنت کدنویسی" icon="📝" meta={p.confidence != null ? <Chip tone="outline">اطمینان {pct(p.confidence)}</Chip> : undefined}>
      <dl className="space-y-1.5 text-sm">
        <div><dt className="inline text-muted">علامت: </dt><dd className="inline">{p.symptom}</dd></div>
        <div><dt className="inline text-muted">علت مشکوک: </dt><dd className="inline">{p.suspected_cause}</dd></div>
        {p.suspected_files?.length > 0 && <div><dt className="inline text-muted">فایل‌های مشکوک: </dt><dd className="inline"><Ltr>{p.suspected_files.join(', ')}</Ltr></dd></div>}
        {p.fix_direction && <div><dt className="text-muted">جهت اصلاح:</dt><dd dir="ltr" className="mono mt-0.5 rounded-lg bg-raised/60 px-2 py-1 text-xs">{p.fix_direction}</dd></div>}
      </dl>
      {p.acceptance_criteria?.length > 0 && (
        <Expander label="معیارهای پذیرش">
          <ul className="space-y-0.5 text-xs text-muted" dir="ltr">
            {p.acceptance_criteria.map((c: string) => (
              <li key={c}>• {c}</li>
            ))}
          </ul>
        </Expander>
      )}
      {p.path && <Ltr className="mt-2 block text-[10px] text-muted">{p.path}</Ltr>}
    </Card>
  )
}

export function LogsCard({ p }: { p: Record<string, any> }) {
  const lines: { type: string; datetime: string; message: string }[] = p.lines ?? []
  return (
    <Card title="لاگ‌ها" icon="📜" meta={<Chip tone="outline"><Ltr>{p.app}</Ltr> · {lines.length} خط</Chip>}>
      <pre className="code max-h-64 overflow-auto">
        {lines.map((l, i) => (
          <div key={i} className={l.type === 'stderr' ? 'text-rose-300' : ''}>
            <span className="opacity-50">{time(l.datetime)}</span>  {l.message}
          </div>
        ))}
      </pre>
    </Card>
  )
}
