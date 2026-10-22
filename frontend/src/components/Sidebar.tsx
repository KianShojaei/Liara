import { useEffect, useState } from 'react'
import { api } from '../api'
import { mb, num, toman } from '../format'
import type { WatchSample } from '../hooks/useSession'
import type { AppOverview, Status } from '../types'
import { Chip, Sparkline } from './ui'

export function Sidebar({ status, samples, selected, onSelect, sessionId, openIncidents }: { status: Status | null; samples: WatchSample[]; selected: string | null; onSelect: (app: string) => void; sessionId: string | null; openIncidents: number }) {
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
    <aside className="space-y-3">
      <div className="card">
        <div className="flex flex-wrap items-center gap-1.5">
          <Chip cls={status?.mode === 'live' ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200' : 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200'} title="حالت اتصال به لیارا">
            {status?.mode === 'live' ? 'متصل به لیارا' : 'حالت شبیه‌سازی (mock)'}
          </Chip>
          <Chip title="مدل زبانی">{status?.llm ? 'LLM فعال' : 'LLM غیرفعال'}</Chip>
          {status?.watcher?.running && <Chip cls="bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-200">پایش فعال</Chip>}
          {status?.circuit_open && <Chip cls="bg-rose-100 text-rose-800">قطع موقت API</Chip>}
        </div>
        {status?.ok ? (
          <div className="mt-3 text-sm">
            <div className="flex justify-between"><span className="text-slate-500">موجودی</span><b>{toman(status.balance)}</b></div>
            <div className="flex justify-between"><span className="text-slate-500">هزینه‌ی ساعتی</span><span>{toman(status.hourly_burn)}</span></div>
            <div className="flex justify-between"><span className="text-slate-500">کفاف موجودی</span><span>{status.runway_label}</span></div>
            <div className="flex justify-between"><span className="text-slate-500">رخدادهای باز</span><span className={openIncidents ? 'text-rose-600 font-semibold' : ''}>{num(openIncidents, 0)}</span></div>
          </div>
        ) : (
          <div className="mt-3 text-sm text-rose-600">{status?.error ?? 'در حال اتصال…'}</div>
        )}
      </div>

      <div className="card">
        <div className="mb-2 text-sm font-semibold">برنامه‌ها</div>
        <ul className="space-y-1">
          {(status?.apps ?? []).map((a) => (
            <li key={a.name}>
              <button onClick={() => onSelect(a.name)} className={`flex w-full items-center gap-2 rounded-xl px-2 py-1.5 text-sm ${selected === a.name ? 'bg-slate-100 dark:bg-slate-800' : 'hover:bg-slate-50 dark:hover:bg-slate-800/50'}`}>
                <span className={`inline-block h-2.5 w-2.5 rounded-full ${a.scale ? (selected === a.name && httpOk === false ? 'bg-rose-500' : 'bg-emerald-500') : 'bg-slate-400'}`} />
                <span className="mono">{a.name}</span>
                <span className="mr-auto text-xs text-slate-500">{a.platform} · {a.plan_id}</span>
              </button>
            </li>
          ))}
          {status?.ok && !status.apps.length && <li className="text-xs text-slate-500">برنامه‌ای وجود ندارد؛ با «دیپلوی ./مسیر» شروع کنید.</li>}
        </ul>
      </div>

      {selected && overview && (
        <div className="card">
          <div className="mb-1 flex items-center justify-between">
            <span className="mono text-sm font-semibold">{selected}</span>
            <Chip cls={httpOk === false ? 'bg-rose-100 text-rose-800' : 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200'}>{httpOk === false ? 'پاسخ نمی‌دهد' : 'در دسترس'}</Chip>
          </div>
          <a href={overview.url} target="_blank" rel="noreferrer" className="mono block truncate text-xs text-emerald-700 underline">{overview.url}</a>
          <div className="mt-2 text-xs text-slate-500">
            پلن {overview.plan?.plan_id ?? overview.app.plan_id} · {overview.plan ? `${num(overview.plan.ram.amount, 2)}GB / ${num(overview.plan.cpu.amount, 1)} CPU · ${toman(overview.plan.price)}/ساعت` : ''}
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <div>
              <div className="text-xs text-slate-500">CPU: {num(nowCpu, 2)} هسته</div>
              <Sparkline points={cpuSeries} color="#f59e0b" />
            </div>
            <div>
              <div className="text-xs text-slate-500">RAM: {mb(nowMem)}</div>
              <Sparkline points={memSeries} color="#6366f1" />
            </div>
          </div>
          <button className="btn-ghost mt-2 w-full text-xs" disabled={busy} onClick={toggleWatch}>
            {overview.watching ? '⏸ توقف پایش خودکار' : '👁 شروع پایش خودکار'}
          </button>
        </div>
      )}
    </aside>
  )
}
