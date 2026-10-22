import { useState } from 'react'
import { STEP_NAMES } from '../format'
import { Card } from './ui'

export interface StepState {
  name: string
  status: string
  detail: string
}

export function StepperCard({ steps, logs }: { steps: StepState[]; logs: string[] }) {
  const [open, setOpen] = useState(false)
  const icon = (s: string) => (s === 'done' ? '✅' : s === 'failed' ? '❌' : '⏳')
  return (
    <Card title="اجرای مراحل" icon="🚀">
      <ol className="space-y-1 text-sm">
        {steps.map((s) => (
          <li key={s.name} className="flex items-center gap-2">
            <span className={s.status === 'running' ? 'animate-pulse' : ''}>{icon(s.status)}</span>
            <span>{STEP_NAMES[s.name] ?? s.name}</span>
            {s.detail && <span className="mono text-xs text-slate-500">{s.detail}</span>}
          </li>
        ))}
      </ol>
      {logs.length > 0 && (
        <>
          <button className="mt-2 text-xs text-slate-500 underline" onClick={() => setOpen(!open)}>
            {open ? 'بستن خروجی' : `خروجی دیپلوی (${logs.length} خط)`}
          </button>
          {open && <pre className="mono mt-1 max-h-56 overflow-auto rounded-lg bg-slate-950 p-2 text-[11px] leading-5 text-slate-100">{logs.join('\n')}</pre>}
        </>
      )}
    </Card>
  )
}
