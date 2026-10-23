import { useEffect, useState } from 'react'
import { api } from '../api'
import { mb, num, toman } from '../format'
import type { WatchSample } from '../hooks/useSession'
import type { AppOverview, Status } from '../types'
import { Button, Chip, Dot, Skeleton, Sparkline } from './ui'

interface Props {
  status: Status | null
  samples: WatchSample[]
  selected: string | null
  onSelect: (app: string) => void
  sessionId: string | null
  openIncidents: number
  onDeployClick: () => void
}

export function StatusPanel({ status, samples, selected, onSelect, sessionId, openIncidents, onDeployClick }: Props) {
  const [overview, setOverview] = useState<AppOverview | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!selected) return
    let alive = true
    const load = () => api.appOverview(selected).then((o) => alive && setOverview(o)).catch(() => alive && setOverview(null))
    load()
    const t = setInterval(load, 30000)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [selected])

  const live = samples.filter((s) => s.app === selected)
  const cpuSeries = [...(overview?.cpu ?? []).map((p) => p[1]), ...live.map((s) => s.cpu ?? 0)].slice(-60)
  const memSeries = [...(overview?.memory ?? []).map((p) => p[1]), ...live.map((s) => s.memory ?? 0)].slice(-60)
  const lastLive = live[live.length - 1]
  const nowCpu = lastLive?.cpu ?? overview?.now?.cpu ?? null
  const nowMem = lastLive?.memory ?? overview?.now?.memory ?? null
  const httpOk = lastLive?.http_ok ?? overview?.probe?.ok ?? null
  const protectedPath = overview?.probe?.protected === true
  const latency = lastLive?.latency_ms ?? overview?.probe?.latency_ms ?? null

  const toggleWatch = async () => {
    if (!selected || !overview) return
    setBusy(true)
    try {
      await api.setWatch(selected, !overview.watching, sessionId ?? '')
      setOverview({ ...overview, watching: !overview.watching })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-3">
      <section className="card">
        <div className="flex flex-wrap items-center gap-1.5">
          <Chip tone={status?.mode === 'live' ? 'success' : 'warning'} title="حالت اتصال به لیارا">
            {status?.mode === 'live' ? '● متصل به لیارا' : '◐ شبیه‌سازی (mock)'}
          </Chip>
          <Chip tone={status?.llm ? 'info' : 'outline'} title="مدل زبانی">{status?.llm ? 'LLM فعال' : 'LLM غیرفعال'}</Chip>
          {status?.watcher?.running && <Chip tone="violet">پایش فعال</Chip>}
          {status?.circuit_open && <Chip tone="danger">قطع موقت API{status.circuit_seconds_left ? ` · ${status.circuit_seconds_left}s` : ''}</Chip>}
        </div>
        {status == null ? (
          <div className="mt-3 space-y-2">
            <Skeleton />
            <Skeleton className="h-4 w-2/3" />
          </div>
        ) : status.ok ? (
          <dl className="mt-3 divide-y divide-line">
            <div className="kpi">
              <dt className="kpi-label">موجودی</dt>
              <dd className="font-semibold">{toman(status.balance)}</dd>
            </div>
            <div className="kpi">
              <dt className="kpi-label">هزینه‌ی ساعتی</dt>
              <dd>{toman(status.hourly_burn)}</dd>
            </div>
            <div className="kpi">
              <dt className="kpi-label">کفاف موجودی</dt>
              <dd>{status.runway_label}</dd>
            </div>
            <div className="kpi">
              <dt className="kpi-label">رخدادهای باز</dt>
              <dd className={openIncidents ? 'font-semibold text-rose-500' : ''}>{num(openIncidents, 0)}</dd>
            </div>
          </dl>
        ) : (
          <div className="mt-3 space-y-1 text-sm text-rose-400">
            <div>{status.error ?? 'در حال اتصال…'}</div>
            {status.last_error && (
              <div className="text-[11px] text-muted" dir="ltr">
                {status.last_error}
              </div>
            )}
            {status.api_base && (
              <div className="text-[11px] text-muted" dir="ltr">
                {status.api_base}
              </div>
            )}
          </div>
        )}
      </section>

      <section className="card">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-sm font-semibold">برنامه‌ها</h3>
          <Button size="sm" variant="ghost" onClick={onDeployClick}>
            + دیپلوی
          </Button>
        </div>
        <ul className="space-y-1">
          {(status?.apps ?? []).map((a) => (
            <li key={a.name}>
              <button onClick={() => onSelect(a.name)} className={`flex w-full items-center gap-2 rounded-xl px-2.5 py-2 text-sm transition-colors ${selected === a.name ? 'bg-raised' : 'hover:bg-raised/60'}`}>
                <Dot tone={a.scale ? (selected === a.name && httpOk === false ? 'danger' : 'success') : 'muted'} />
                <span dir="ltr" className="mono font-medium">{a.name}</span>
                <span className="mr-auto text-xs text-muted">
                  {a.platform} · <span dir="ltr">{a.plan_id}</span>
                </span>
              </button>
            </li>
          ))}
          {status?.ok && !status.apps.length && <li className="py-2 text-xs text-muted">هنوز برنامه‌ای ندارید. از «پروژه‌ها» شروع کنید.</li>}
        </ul>
      </section>

      {selected && (
        <section className="card bg-gradient-to-b from-surface to-surface/60">
          {!overview ? (
            <div className="space-y-2">
              <Skeleton className="h-5 w-1/2" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : (
            <>
              <div className="mb-1 flex items-center justify-between gap-2">
                <span dir="ltr" className="mono text-sm font-semibold">{selected}</span>
                <Chip tone={httpOk === false ? 'danger' : protectedPath ? 'warning' : 'success'} title={protectedPath ? 'برنامه بالاست ولی این مسیر نیاز به ورود دارد (401/403)' : undefined}>{httpOk === false ? 'پاسخ نمی‌دهد' : protectedPath ? 'بالا · نیاز به ورود' : 'در دسترس'}</Chip>
              </div>
              <a href={overview.url} target="_blank" rel="noreferrer" dir="ltr" className="mono block truncate text-xs text-emerald-500 hover:underline">
                {overview.url}
              </a>
              <div className="mt-2 text-xs text-muted">
                پلن <span dir="ltr">{overview.plan?.plan_id ?? overview.app.plan_id}</span>
                {overview.plan && ` · ${num(overview.plan.ram.amount, 2)}GB / ${num(overview.plan.cpu.amount, 1)} CPU · ${toman(overview.plan.price)}/ساعت`}
                {latency != null && ` · ${num(latency, 0)}ms`}
              </div>
              <div className="mt-3 grid grid-cols-2 gap-3">
                <div>
                  <div className="mb-1 flex items-baseline justify-between text-xs">
                    <span className="text-muted">CPU</span>
                    <span className="font-medium">{num(nowCpu, 2)} هسته</span>
                  </div>
                  <Sparkline points={cpuSeries} color="#f59e0b" />
                </div>
                <div>
                  <div className="mb-1 flex items-baseline justify-between text-xs">
                    <span className="text-muted">RAM</span>
                    <span className="font-medium">{mb(nowMem)}</span>
                  </div>
                  <Sparkline points={memSeries} color="#818cf8" />
                </div>
              </div>
              <Button variant="ghost" size="sm" className="mt-3 w-full" loading={busy} onClick={toggleWatch}>
                {overview.watching ? '⏸ توقف پایش خودکار' : '👁 شروع پایش خودکار'}
              </Button>
            </>
          )}
        </section>
      )}
    </div>
  )
}
