import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { Composer } from './components/Composer'
import { AuditPanel, IncidentsPanel, LimitationsPanel, PolicyPanel } from './components/Panels'
import { ProjectsView } from './components/Projects'
import { StatusPanel } from './components/Sidebar'
import { Timeline } from './components/Timeline'
import { Dot } from './components/ui'
import { useSession } from './hooks/useSession'
import { applyTheme, savedTheme, type Theme } from './theme'
import type { Incident, Status } from './types'

type View = 'chat' | 'projects' | 'incidents' | 'audit' | 'limitations' | 'policy'
const VIEWS: { id: View; label: string; icon: string }[] = [
  { id: 'chat', label: 'گفتگو', icon: '💬' },
  { id: 'projects', label: 'پروژه‌ها', icon: '📦' },
  { id: 'incidents', label: 'رخدادها', icon: '🚨' },
  { id: 'audit', label: 'ثبت وقایع', icon: '📒' },
  { id: 'limitations', label: 'محدودیت‌ها', icon: '🖐️' },
  { id: 'policy', label: 'سطوح ریسک', icon: '🛡️' },
]

const EMPTY_STATUS: Status = { ok: false, mode: 'mock', llm: false, balance: 0, hourly_burn: 0, runway_hours: null, runway_label: '—', apps: [], watcher: { running: false, apps: [] }, circuit_open: false }

export default function App() {
  const { sessionId, events, connected, samples, newSession, send } = useSession()
  const [theme, setTheme] = useState<Theme>(savedTheme)
  const [status, setStatus] = useState<Status | null>(null)
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [selectedApp, setSelectedApp] = useState<string | null>(null)
  const [view, setView] = useState<View>('chat')
  const [drawer, setDrawer] = useState(false)

  const toggleTheme = () => {
    const next: Theme = theme === 'dark' ? 'light' : 'dark'
    applyTheme(next)
    setTheme(next)
  }

  const refresh = useCallback(() => {
    api.status().then(setStatus).catch((e) => setStatus({ ...EMPTY_STATUS, error: String(e.message) }))
    api.incidents().then(setIncidents).catch(() => undefined)
  }, [])

  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 20000)
    return () => clearInterval(t)
  }, [refresh])

  useEffect(() => {
    const last = events[events.length - 1]
    if (last && ['proposal_update', 'verification', 'success', 'incident', 'step'].includes(last.kind)) refresh()
  }, [events, refresh])

  useEffect(() => {
    if (!selectedApp && status?.apps?.length) setSelectedApp(status.apps[0].name)
  }, [status, selectedApp])

  const sessionApp = useMemo(() => {
    for (let i = events.length - 1; i >= 0; i--) {
      const p = events[i].payload
      if (p.app && typeof p.app === 'string') return p.app as string
      if (p.app_name) return p.app_name as string
    }
    return selectedApp ?? undefined
  }, [events, selectedApp])

  const openIncidents = incidents.filter((i) => i.status === 'open' || i.status === 'investigated').length

  const startDeploy = async (path: string, app: string) => {
    const id = sessionId ?? (await newSession())
    await api.wizardStart(id, path, app)
    setView('chat')
  }

  const nav = (
    <nav className="flex flex-col gap-1" aria-label="بخش‌ها">
      {VIEWS.map((v) => (
        <button key={v.id} onClick={() => setView(v.id)} className={`nav-item ${view === v.id ? 'nav-item-active' : ''}`} aria-current={view === v.id ? 'page' : undefined}>
          <span aria-hidden className="w-5 text-center text-base">
            {v.icon}
          </span>
          <span className="flex-1 text-right">{v.label}</span>
          {v.id === 'incidents' && openIncidents > 0 && <span className="rounded-full bg-rose-500 px-1.5 text-[10px] font-semibold text-white">{openIncidents}</span>}
        </button>
      ))}
    </nav>
  )

  return (
    <div className="flex min-h-screen">
      {/* nav rail (right in RTL) */}
      <aside className="sticky top-0 hidden h-screen w-56 shrink-0 flex-col border-l border-line bg-surface/60 p-4 md:flex">
        <div className="mb-6 flex items-center gap-2 px-1">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-emerald-500/15 text-lg" aria-hidden>
            🧭
          </span>
          <div className="leading-tight">
            <div className="text-sm font-semibold">Liara Ops Copilot</div>
            <div className="text-[11px] text-muted">همکار فنی شما</div>
          </div>
        </div>
        {nav}
        <div className="mt-auto space-y-2 pt-4">
          <button className="btn-primary w-full" onClick={() => { newSession(); setView('chat') }}>
            + گفتگوی جدید
          </button>
          <button className="btn-ghost btn-sm w-full" onClick={toggleTheme} title="تغییر تم">
            {theme === 'dark' ? '☀️ تم روشن' : '🌙 تم تاریک'}
          </button>
        </div>
      </aside>

      {/* main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex items-center gap-2 border-b border-line bg-bg/85 px-4 py-2.5 backdrop-blur md:px-6">
          <span className="text-sm font-semibold md:hidden">🧭 Copilot</span>
          <h1 className="hidden text-sm font-semibold md:block">{VIEWS.find((v) => v.id === view)?.label}</h1>
          <div className="mr-auto flex items-center gap-2 text-xs text-muted">
            {view === 'chat' && sessionId && (
              <span className="hidden items-center gap-1.5 sm:inline-flex">
                <Dot tone={connected ? 'success' : 'warning'} pulse={!connected} />
                {connected ? 'متصل' : 'اتصال مجدد…'}
                {sessionApp && (
                  <>
                    <span className="opacity-40">·</span>
                    <span dir="ltr" className="mono">{sessionApp}</span>
                  </>
                )}
              </span>
            )}
            <button className="btn-ghost btn-sm md:hidden" onClick={toggleTheme} aria-label="تغییر تم">
              {theme === 'dark' ? '☀️' : '🌙'}
            </button>
            <button className="btn-ghost btn-sm md:hidden" onClick={() => { newSession(); setView('chat') }}>
              + جدید
            </button>
            <button className="btn-ghost btn-sm xl:hidden" onClick={() => setDrawer(true)}>
              وضعیت
            </button>
          </div>
        </header>

        <div className="flex min-w-0 flex-1">
          <main className="min-w-0 flex-1 px-4 pb-24 pt-4 md:px-6 md:pb-6">
            {view === 'chat' && sessionId && (
              <div className="mx-auto flex h-[calc(100vh-7.5rem)] max-w-3xl flex-col md:h-[calc(100vh-5.5rem)]">
                <div className="flex-1 overflow-y-auto pl-1">
                  <Timeline events={events} sessionId={sessionId} app={sessionApp} onStartDeploy={startDeploy} />
                </div>
                <div className="pt-3">
                  <Composer onSend={(t) => send(t, selectedApp ?? undefined)} disabled={!connected && events.length === 0} />
                </div>
              </div>
            )}
            {view === 'projects' && <ProjectsView onDeploy={startDeploy} />}
            {view === 'incidents' && <IncidentsPanel sessionId={sessionId ?? ''} onOpenChat={() => setView('chat')} />}
            {view === 'audit' && <AuditPanel />}
            {view === 'limitations' && <LimitationsPanel />}
            {view === 'policy' && <PolicyPanel />}
          </main>

          {/* status panel (left in RTL) on xl; drawer below */}
          <aside className="sticky top-[3.1rem] hidden h-[calc(100vh-3.1rem)] w-80 shrink-0 overflow-y-auto border-r border-line p-4 xl:block">
            <StatusPanel status={status} samples={samples} selected={selectedApp} onSelect={setSelectedApp} sessionId={sessionId} openIncidents={openIncidents} onDeployClick={() => setView('projects')} />
          </aside>
        </div>
      </div>

      {drawer && (
        <div className="fixed inset-0 z-40 xl:hidden" role="dialog" aria-label="پنل وضعیت">
          <div className="absolute inset-0 bg-slate-950/60 backdrop-blur-sm" onClick={() => setDrawer(false)} />
          <div className="absolute left-0 top-0 h-full w-[min(22rem,92vw)] overflow-y-auto border-r border-line bg-bg p-4 shadow-2xl">
            <div className="mb-3 flex items-center justify-between">
              <span className="text-sm font-semibold">وضعیت</span>
              <button className="btn-ghost btn-sm" onClick={() => setDrawer(false)}>
                بستن
              </button>
            </div>
            <StatusPanel status={status} samples={samples} selected={selectedApp} onSelect={setSelectedApp} sessionId={sessionId} openIncidents={openIncidents} onDeployClick={() => { setDrawer(false); setView('projects') }} />
          </div>
        </div>
      )}

      {/* bottom tab bar on mobile */}
      <nav className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-6 border-t border-line bg-surface/95 backdrop-blur md:hidden" aria-label="بخش‌ها">
        {VIEWS.map((v) => (
          <button key={v.id} onClick={() => setView(v.id)} className={`flex flex-col items-center gap-0.5 py-2 text-[10px] ${view === v.id ? 'text-emerald-500' : 'text-muted'}`}>
            <span className="relative text-base" aria-hidden>
              {v.icon}
              {v.id === 'incidents' && openIncidents > 0 && <span className="absolute -left-2 -top-1 rounded-full bg-rose-500 px-1 text-[9px] text-white">{openIncidents}</span>}
            </span>
            {v.label}
          </button>
        ))}
      </nav>
    </div>
  )
}
