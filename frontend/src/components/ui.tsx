import type { ReactNode } from 'react'

export function Chip({ children, cls = 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200', title }: { children: ReactNode; cls?: string; title?: string }) {
  return (
    <span className={`chip ${cls}`} title={title}>
      {children}
    </span>
  )
}

export function Card({ children, tone = 'default', title, icon }: { children: ReactNode; tone?: 'default' | 'success' | 'error' | 'warning' | 'info'; title?: string; icon?: string }) {
  const tones: Record<string, string> = {
    default: '',
    success: 'border-emerald-300 dark:border-emerald-800',
    error: 'border-rose-300 dark:border-rose-800',
    warning: 'border-amber-300 dark:border-amber-800',
    info: 'border-sky-300 dark:border-sky-800',
  }
  return (
    <div className={`card ${tones[tone]}`}>
      {title && (
        <div className="mb-2 flex items-center gap-2 font-semibold">
          {icon && <span aria-hidden>{icon}</span>}
          <span>{title}</span>
        </div>
      )}
      {children}
    </div>
  )
}

export function Sparkline({ points, color = '#10b981', height = 36, width = 160 }: { points: number[]; color?: string; height?: number; width?: number }) {
  if (points.length < 2) return <svg width={width} height={height} />
  const min = Math.min(...points)
  const max = Math.max(...points)
  const span = max - min || 1
  const step = width / (points.length - 1)
  const d = points.map((v, i) => `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(1)},${(height - 2 - ((v - min) / span) * (height - 4)).toFixed(1)}`).join(' ')
  return (
    <svg width={width} height={height} className="overflow-visible" style={{ direction: 'ltr' }}>
      <path d={d} fill="none" stroke={color} strokeWidth="1.5" />
    </svg>
  )
}

export function LineChart({ series, height = 120 }: { series: { label: string; points: [number, number][]; color: string; unit?: (v: number) => string }[]; height?: number }) {
  const width = 480
  const all = series.filter((s) => s.points.length > 1)
  if (!all.length) return <div className="text-xs text-slate-500">داده‌ای برای نمودار نیست.</div>
  return (
    <div className="space-y-2">
      {all.map((s) => {
        const vals = s.points.map((p) => p[1])
        const min = Math.min(...vals)
        const max = Math.max(...vals)
        const span = max - min || 1
        const step = width / (vals.length - 1)
        const d = vals.map((v, i) => `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(1)},${(height - 6 - ((v - min) / span) * (height - 12)).toFixed(1)}`).join(' ')
        const fmt = s.unit ?? ((v: number) => v.toFixed(2))
        return (
          <div key={s.label}>
            <div className="mb-1 flex items-center justify-between text-xs text-slate-500">
              <span>{s.label}</span>
              <span className="mono">{fmt(min)} … {fmt(max)}</span>
            </div>
            <svg viewBox={`0 0 ${width} ${height}`} className="h-24 w-full rounded-lg bg-slate-50 dark:bg-slate-950" style={{ direction: 'ltr' }} preserveAspectRatio="none">
              <path d={d} fill="none" stroke={s.color} strokeWidth="2" vectorEffect="non-scaling-stroke" />
            </svg>
          </div>
        )
      })}
    </div>
  )
}

export function Check({ ok }: { ok: boolean }) {
  return <span className={ok ? 'text-emerald-600' : 'text-rose-600'}>{ok ? '✓' : '✗'}</span>
}
