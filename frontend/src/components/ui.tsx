import { useState, type ReactNode } from 'react'
import type { Tone } from '../format'

export function Chip({ children, tone = 'neutral', title, className = '' }: { children: ReactNode; tone?: Tone; title?: string; className?: string }) {
  return (
    <span className={`chip chip-${tone} ${className}`} title={title}>
      {children}
    </span>
  )
}

export type CardTone = 'default' | 'success' | 'error' | 'warning' | 'info' | 'accent'

export function Card({ children, tone = 'default', title, icon, meta, className = '', id }: { children: ReactNode; tone?: CardTone; title?: ReactNode; icon?: string; meta?: ReactNode; className?: string; id?: string }) {
  return (
    <section id={id} className={`card animate-rise ${tone !== 'default' ? `card-tone-${tone}` : ''} ${className}`}>
      {(title || meta) && (
        <header className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            {icon && (
              <span aria-hidden className="grid h-7 w-7 place-items-center rounded-lg bg-raised text-base">
                {icon}
              </span>
            )}
            <span>{title}</span>
          </h3>
          {meta && <div className="flex flex-wrap items-center gap-1.5">{meta}</div>}
        </header>
      )}
      {children}
    </section>
  )
}

export function Button({ children, variant = 'secondary', size = 'md', loading, className = '', ...rest }: { children: ReactNode; variant?: 'primary' | 'secondary' | 'ghost' | 'danger'; size?: 'sm' | 'md'; loading?: boolean } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button className={`btn-${variant} ${size === 'sm' ? 'btn-sm' : ''} ${className}`} disabled={rest.disabled || loading} {...rest}>
      {loading && <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />}
      {children}
    </button>
  )
}

export function Expander({ label, children, defaultOpen = false }: { label: string; children: ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="mt-3">
      <button className="flex items-center gap-1 text-xs text-muted hover:text-ink" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className={`inline-block transition-transform ${open ? 'rotate-90' : ''}`}>◂</span>
        {label}
      </button>
      {open && <div className="mt-2 animate-rise">{children}</div>}
    </div>
  )
}

export function Skeleton({ className = 'h-4 w-full' }: { className?: string }) {
  return <div className={`skeleton ${className}`} />
}

export function Empty({ icon = '◌', title, hint, action }: { icon?: string; title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-line px-6 py-10 text-center">
      <span className="text-3xl text-muted/70" aria-hidden>
        {icon}
      </span>
      <div className="text-sm font-medium">{title}</div>
      {hint && <div className="max-w-sm text-xs text-muted">{hint}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}

export function Dot({ tone = 'success', pulse }: { tone?: 'success' | 'danger' | 'warning' | 'muted'; pulse?: boolean }) {
  const c = { success: 'bg-emerald-500', danger: 'bg-rose-500', warning: 'bg-amber-400', muted: 'bg-slate-500' }[tone]
  return (
    <span className="relative inline-flex h-2.5 w-2.5">
      {pulse && <span className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-60 ${c}`} />}
      <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${c}`} />
    </span>
  )
}

export function Check({ ok }: { ok: boolean }) {
  return <span className={`inline-grid h-5 w-5 place-items-center rounded-full text-[11px] font-bold ${ok ? 'bg-emerald-500/15 text-emerald-500' : 'bg-rose-500/15 text-rose-500'}`}>{ok ? '✓' : '✗'}</span>
}

export function Sparkline({ points, color = '#10b981', height = 40, width = 160 }: { points: number[]; color?: string; height?: number; width?: number }) {
  if (points.length < 2) return <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} />
  const min = Math.min(...points)
  const max = Math.max(...points)
  const span = max - min || 1
  const step = width / (points.length - 1)
  const pts = points.map((v, i) => [i * step, height - 3 - ((v - min) / span) * (height - 8)] as const)
  const d = pts.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  const id = `g${color.replace('#', '')}`
  return (
    <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className="overflow-visible" style={{ direction: 'ltr' }}>
      <defs>
        <linearGradient id={id} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.35" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${d} L${width},${height} L0,${height} Z`} fill={`url(#${id})`} />
      <path d={d} fill="none" stroke={color} strokeWidth="1.5" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
    </svg>
  )
}

export interface Series {
  label: string
  points: [number, number][]
  color: string
  unit?: (v: number) => string
  threshold?: number
  thresholdLabel?: string
}

/** Line chart with y-axis labels, time ticks and an optional threshold band. */
export function LineChart({ series, height = 150 }: { series: Series[]; height?: number }) {
  const all = series.filter((s) => s.points.length > 1)
  if (!all.length) return <div className="text-xs text-muted">داده‌ای برای نمودار نیست.</div>
  const W = 520
  const padL = 44
  const padB = 18
  const padT = 8
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {all.map((s) => {
        const vals = s.points.map((p) => p[1])
        const ts = s.points.map((p) => p[0])
        const min = Math.min(...vals, s.threshold ?? Infinity) * 0.98
        const max = Math.max(...vals, s.threshold ?? -Infinity) * 1.04 || 1
        const span = max - min || 1
        const x = (i: number) => padL + (i / (vals.length - 1)) * (W - padL - 6)
        const y = (v: number) => padT + (1 - (v - min) / span) * (height - padT - padB)
        const d = vals.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ')
        const fmt = s.unit ?? ((v: number) => v.toFixed(2))
        const gridY = [0, 0.5, 1].map((k) => min + k * span)
        const t0 = new Date(ts[0] * 1000)
        const t1 = new Date(ts[ts.length - 1] * 1000)
        const tf = (d: Date) => d.toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' })
        const last = vals[vals.length - 1]
        return (
          <div key={s.label} className="rounded-xl border border-line bg-bg/60 p-2">
            <div className="mb-1 flex items-center justify-between text-xs">
              <span className="font-medium">{s.label}</span>
              <span className="mono text-muted">اکنون {fmt(last)}</span>
            </div>
            <svg viewBox={`0 0 ${W} ${height}`} className="w-full" style={{ direction: 'ltr', height }} preserveAspectRatio="none" role="img" aria-label={s.label}>
              {gridY.map((g) => (
                <g key={g}>
                  <line x1={padL} x2={W - 6} y1={y(g)} y2={y(g)} stroke="currentColor" strokeOpacity="0.12" strokeDasharray="3 4" />
                  <text x={padL - 6} y={y(g) + 3.5} fontSize="9.5" textAnchor="end" fill="currentColor" fillOpacity="0.6">
                    {fmt(g)}
                  </text>
                </g>
              ))}
              {s.threshold != null && (
                <g>
                  <rect x={padL} y={padT} width={W - padL - 6} height={Math.max(0, y(s.threshold) - padT)} fill="#f43f5e" fillOpacity="0.07" />
                  <line x1={padL} x2={W - 6} y1={y(s.threshold)} y2={y(s.threshold)} stroke="#f43f5e" strokeOpacity="0.7" strokeDasharray="4 3" />
                  <text x={W - 8} y={y(s.threshold) - 3} fontSize="9.5" textAnchor="end" fill="#f43f5e">
                    {s.thresholdLabel ?? 'سقف'}
                  </text>
                </g>
              )}
              <path d={`${d} L${x(vals.length - 1)},${height - padB} L${padL},${height - padB} Z`} fill={s.color} fillOpacity="0.12" />
              <path d={d} fill="none" stroke={s.color} strokeWidth="2" vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
              <circle cx={x(vals.length - 1)} cy={y(last)} r="3" fill={s.color} />
              <text x={padL} y={height - 4} fontSize="9.5" fill="currentColor" fillOpacity="0.6">
                {tf(t0)}
              </text>
              <text x={W - 6} y={height - 4} fontSize="9.5" textAnchor="end" fill="currentColor" fillOpacity="0.6">
                {tf(t1)}
              </text>
            </svg>
          </div>
        )
      })}
    </div>
  )
}

export function Progress({ value, tone = 'success' }: { value: number; tone?: 'success' | 'info' | 'warning' }) {
  const c = { success: 'bg-emerald-500', info: 'bg-sky-400', warning: 'bg-amber-400' }[tone]
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-raised">
      <div className={`h-full rounded-full transition-all ${c}`} style={{ width: `${Math.max(0, Math.min(100, value * 100))}%` }} />
    </div>
  )
}

export function Ltr({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <span dir="ltr" className={`mono inline-block ${className}`}>
      {children}
    </span>
  )
}
