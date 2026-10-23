import { CheckIcon, RocketIcon, XIcon } from './icons'
import { STEP_NAMES } from '../format'
import { Card, Expander, Ltr } from './ui'

export interface StepState {
  name: string
  status: string
  detail: string
}

export function StepperCard({ steps, logs }: { steps: StepState[]; logs: string[] }) {
  const done = steps.filter((s) => s.status === 'done').length
  const failed = steps.some((s) => s.status === 'failed')
  const running = steps.some((s) => s.status === 'running')
  return (
    <Card title="اجرای مراحل" icon={<RocketIcon size={18} />} meta={<span className="text-xs text-muted">{done} از {steps.length}</span>}>
      <ol className="relative space-y-3 pr-1">
        {steps.map((s, i) => {
          const last = i === steps.length - 1
          return (
            <li key={s.name} className="relative flex items-start gap-3">
              {!last && <span className={`absolute right-[11px] top-6 h-[calc(100%-0.25rem)] w-0.5 ${s.status === 'done' ? 'bg-emerald-500' : 'bg-line'} ${s.status === 'running' ? 'animate-flow bg-[linear-gradient(to_bottom,#10b981_50%,transparent_50%)] bg-[length:100%_12px]' : ''}`} aria-hidden />}
              <span className={`relative z-10 grid h-6 w-6 shrink-0 place-items-center rounded-full text-[11px] font-bold ${s.status === 'done' ? 'bg-emerald-500 text-white dark:text-slate-950' : s.status === 'failed' ? 'bg-rose-500 text-white' : s.status === 'running' ? 'bg-emerald-500/20 text-emerald-500 ring-2 ring-emerald-500/50' : 'bg-raised text-muted'}`}>
                {s.status === 'done' ? <CheckIcon size={13} strokeWidth={2.5} /> : s.status === 'failed' ? <XIcon size={13} strokeWidth={2.5} /> : s.status === 'running' ? <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-500" /> : i + 1}
              </span>
              <div className="min-w-0 pt-0.5">
                <div className={`text-sm ${s.status === 'running' ? 'font-medium' : ''}`}>{STEP_NAMES[s.name] ?? s.name}</div>
                {s.detail && <Ltr className="block truncate text-xs text-muted">{s.detail}</Ltr>}
              </div>
            </li>
          )
        })}
      </ol>
      {failed && <div className="mt-3 text-xs text-rose-400">یکی از مراحل ناموفق بود؛ جزئیات در کارت خطا.</div>}
      {running && !failed && <div className="mt-3 text-xs text-muted">در حال اجرا… این کارت به‌صورت زنده به‌روز می‌شود.</div>}
      {logs.length > 0 && (
        <Expander label={`خروجی دیپلوی (${logs.length} خط)`}>
          <pre className="code max-h-56 overflow-auto">{logs.join('\n')}</pre>
        </Expander>
      )}
    </Card>
  )
}
