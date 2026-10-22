import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { TimelineEvent } from '../types'

const KEY = 'copilot.session'

export interface WatchSample {
  app: string
  ts: number
  cpu: number | null
  memory: number | null
  http_ok: boolean | null
  latency_ms: number | null
}

export function useSession() {
  const [sessionId, setSessionId] = useState<string | null>(() => {
    try {
      return localStorage.getItem(KEY)
    } catch {
      return null
    }
  })
  const [events, setEvents] = useState<TimelineEvent[]>([])
  const [connected, setConnected] = useState(false)
  const [samples, setSamples] = useState<WatchSample[]>([])
  const lastSeq = useRef(0)

  // Pure updater (StrictMode may invoke it twice): dedupe against the previous list only.
  const pushEvents = useCallback((incoming: TimelineEvent[]) => {
    setEvents((prev) => {
      const known = new Set(prev.map((e) => e.id))
      const fresh = incoming.filter((e) => e.id && !known.has(e.id))
      if (!fresh.length) return prev
      return [...prev, ...fresh].sort((a, b) => a.seq - b.seq)
    })
  }, [])

  useEffect(() => {
    lastSeq.current = events.length ? events[events.length - 1].seq : 0
  }, [events])

  const newSession = useCallback(async (title = 'گفتگوی جدید') => {
    const s = await api.createSession(title)
    lastSeq.current = 0
    setEvents([])
    setSessionId(s.id)
    try {
      localStorage.setItem(KEY, s.id)
    } catch {
      /* ignore */
    }
    return s.id
  }, [])

  const switchSession = useCallback((id: string) => {
    lastSeq.current = 0
    setEvents([])
    setSessionId(id)
    try {
      localStorage.setItem(KEY, id)
    } catch {
      /* ignore */
    }
  }, [])

  // Ensure a session exists (guard against StrictMode double effects)
  const creating = useRef(false)
  useEffect(() => {
    if (sessionId || creating.current) return
    creating.current = true
    newSession().catch(() => undefined).finally(() => { creating.current = false })
  }, [sessionId, newSession])

  // Timeline fetch + SSE with reconnect
  useEffect(() => {
    if (!sessionId) return
    let stopped = false
    let source: EventSource | null = null
    let retry = 1000

    const load = async () => {
      try {
        pushEvents(await api.timeline(sessionId, 0))
      } catch (err) {
        // session may not exist on this backend anymore
        if (String(err).startsWith('Error: 404')) {
          localStorage.removeItem(KEY)
          setSessionId(null)
        }
      }
    }

    const connect = () => {
      if (stopped) return
      source = new EventSource(`/api/sessions/${sessionId}/events`)
      source.onopen = () => {
        setConnected(true)
        retry = 1000
        // catch up on anything missed while disconnected
        api.timeline(sessionId, lastSeq.current).then(pushEvents).catch(() => undefined)
      }
      source.onmessage = (m) => handle(m.data)
      source.onerror = () => {
        setConnected(false)
        source?.close()
        setTimeout(connect, retry)
        retry = Math.min(retry * 2, 15000)
      }
      // named events: listen for every kind by hooking a generic listener per known kind is impossible;
      // the backend emits `event: <kind>`, so subscribe to the kinds we render.
      KINDS.forEach((k) => source!.addEventListener(k, (m) => handle((m as MessageEvent).data)))
      source.addEventListener('watch_sample', (m) => {
        try {
          const data = JSON.parse((m as MessageEvent).data)
          const p = data.payload as WatchSample
          setSamples((prev) => [...prev.slice(-300), p])
        } catch {
          /* ignore */
        }
      })
    }

    const handle = (raw: string) => {
      try {
        const data = JSON.parse(raw)
        if (data && data.id && data.kind) pushEvents([data])
      } catch {
        /* ignore */
      }
    }

    load().then(connect)
    return () => {
      stopped = true
      source?.close()
    }
  }, [sessionId, pushEvents])

  const send = useCallback(
    async (text: string, app?: string, path?: string) => {
      if (!sessionId) return
      await api.sendMessage(sessionId, text, app, path)
    },
    [sessionId],
  )

  return { sessionId, events, connected, samples, newSession, switchSession, send }
}

const KINDS = [
  'message', 'status', 'notice', 'error', 'success', 'analysis', 'plan_options', 'manual_step', 'env_form',
  'proposal', 'proposal_update', 'step', 'deploy_log', 'verification', 'incident', 'evidence', 'hypotheses',
  'remediation', 'logs', 'fix_brief', 'patch', 'verify_round',
]
