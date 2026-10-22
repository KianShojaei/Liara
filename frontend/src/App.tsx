import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from './api'
import { Composer } from './components/Composer'
import { AuditPanel, IncidentsPanel, LimitationsPanel, PolicyPanel } from './components/Panels'
import { Sidebar } from './components/Sidebar'
import { Timeline } from './components/Timeline'
import { useSession } from './hooks/useSession'
import { applyTheme, savedTheme, type Theme } from './theme'
import type { Incident, Status } from './types'

type View = 'chat' | 'incidents' | 'audit' | 'limitations' | 'policy'
const VIEWS: { id: View; label: string }[] = [
  { id: 'chat', label: 'گفتگو' },
  { id: 'incidents', label: 'رخدادها' },
  { id: 'audit', label: 'ثبت وقایع' },
  { id: 'limitations', label: 'محدودیت‌های API' },
  { id: 'policy', label: 'سطوح ریسک' },
]

export default function App() {
  const { sessionId, events, connected, samples, newSession, send } = useSession()
  const [theme, setTheme] = useState<Theme>(savedTheme)
  const toggleTheme = () => {
    const next: Theme = theme === 'dark' ? 'light' : 'dark'
    applyTheme(next)
    setTheme(next)
  }
  const [status, setStatus] = useState<Status | null>(null)
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [selectedApp, setSelectedApp] = useState<string | null>(null)
  const [view, setView] = useState<View>('chat')
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const refresh = useCallback(() => {
    api.status().then(setStatus).catch((e) => setStatus({ ok: false, error: String(e.message), mode: 'mock', llm: false, balance: 0, hourly_burn: 0, runway_hours: null, runway_label: '—', apps: [], watcher: { running: false, apps: [] }, circuit_open: false }))
    api.incidents().then(setIncidents).catch(() => undefined)
  }, [])

  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 20000)
    return () => clearInterval(t)
  }, [refresh])

  // refresh status after any state-changing event
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

  return (
    <div className="mx-auto flex min-h-screen max-w-7xl flex-col px-4">
      <header className="sticky top-0 z-10 -mx-4 flex flex-wrap items-center gap-2 border-b border-slate-200 bg-slate-50/90 px-4 py-2 backdrop-blur dark:border-slate-800 dark:bg-slate-950/90 sm:gap-3">
        <span className="whitespace-nowrap text-base font-bold sm:text-lg">🧭 Liara Ops Copilot</span>
        <span className="hidden text-xs text-slate-500 md:inline">همکار فنی شما برای دیپلوی، پایش و رفع مشکل</span>
        <nav className="order-last flex w-full gap-1 overflow-x-auto sm:order-none sm:mr-auto sm:w-auto">
          {VIEWS.map((v) => (
            <button key={v.id} onClick={() => setView(v.id)} className={`whitespace-nowrap rounded-xl px-3 py-1 text-sm ${view === v.id ? 'bg-emerald-600 text-white' : 'hover:bg-slate-200 dark:hover:bg-slate-800'}`}>
              {v.label}
              {v.id === 'incidents' && openIncidents > 0 && <span className="mr-1 rounded-full bg-rose-600 px-1.5 text-[10px] text-white">{openIncidents}</span>}
            </button>
          ))}
        </nav>
        <button className="btn-ghost mr-auto whitespace-nowrap text-xs sm:mr-0" onClick={() => newSession()}>+ گفتگوی جدید</button>
        <button className="btn-ghost whitespace-nowrap text-xs" title="تغییر تم" onClick={toggleTheme}>{theme === 'dark' ? '☀️ روشن' : '🌙 تاریک'}</button>
        <button className="btn-ghost whitespace-nowrap text-xs lg:hidden" onClick={() => setSidebarOpen(!sidebarOpen)}>وضعیت</button>
      </header>

      <div className="grid flex-1 gap-4 py-4 lg:grid-cols-[1fr_300px]">
        <main className="min-w-0">
          {view === 'chat' && sessionId && (
            <div className="flex h-[calc(100vh-7rem)] flex-col">
              <div className="mb-2 flex items-center gap-2 text-xs text-slate-500">
                <span className={`inline-block h-2 w-2 rounded-full ${connected ? 'bg-emerald-500' : 'bg-amber-500'}`} />
                {connected ? 'متصل' : 'در حال اتصال مجدد…'} · جلسه <span className="mono">{sessionId}</span>
                {sessionApp && <span>· برنامه <span className="mono">{sessionApp}</span></span>}
              </div>
              <div className="flex-1 overflow-y-auto pl-1">
                <Timeline events={events} sessionId={sessionId} app={sessionApp} />
              </div>
              <div className="pt-3">
                <Composer onSend={(t) => send(t, selectedApp ?? undefined)} disabled={!connected && events.length === 0} />
              </div>
            </div>
          )}
          {view === 'incidents' && <IncidentsPanel sessionId={sessionId ?? ''} onOpenChat={() => setView('chat')} />}
          {view === 'audit' && <AuditPanel />}
          {view === 'limitations' && <LimitationsPanel />}
          {view === 'policy' && <PolicyPanel />}
        </main>
        <div className={`${sidebarOpen ? 'block' : 'hidden'} lg:block`}>
          <Sidebar status={status} samples={samples} selected={selectedApp} onSelect={setSelectedApp} sessionId={sessionId} openIncidents={openIncidents} />
        </div>
      </div>
    </div>
  )
}
