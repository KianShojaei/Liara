import { useRef, useState, type KeyboardEvent } from 'react'
import { Button } from './ui'

const QUICK = ['وضعیت', 'سایت کند شده', 'موجودی', 'ری‌استارت', 'لاگ‌ها']

export function Composer({ onSend, disabled }: { onSend: (t: string) => Promise<void> | void; disabled?: boolean }) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const ref = useRef<HTMLTextAreaElement>(null)

  const submit = async (t: string) => {
    const v = t.trim()
    if (!v || busy) return
    setBusy(true)
    try {
      await onSend(v)
      setText('')
      if (ref.current) ref.current.style.height = 'auto'
    } finally {
      setBusy(false)
      ref.current?.focus()
    }
  }

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit(text)
    }
  }

  const grow = (el: HTMLTextAreaElement) => {
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 160) + 'px'
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {QUICK.map((q) => (
          <button key={q} className="chip chip-outline hover:border-emerald-500/60 hover:text-ink" onClick={() => submit(q)} disabled={disabled || busy}>
            {q}
          </button>
        ))}
      </div>
      <form
        className="flex items-end gap-2 rounded-2xl border border-line bg-surface p-1.5 pr-3 shadow-card focus-within:border-emerald-500/60"
        onSubmit={(e) => {
          e.preventDefault()
          submit(text)
        }}
      >
        <textarea
          ref={ref}
          rows={1}
          className="max-h-40 min-h-[2.25rem] flex-1 resize-none bg-transparent py-1.5 text-sm outline-none placeholder:text-muted/70"
          value={text}
          onChange={(e) => {
            setText(e.target.value)
            grow(e.target)
          }}
          onKeyDown={onKey}
          placeholder="مثلاً: سایت shop-demo کند شده، بررسی کن"
          disabled={disabled}
          aria-label="پیام"
        />
        <Button variant="primary" type="submit" loading={busy} disabled={disabled || !text.trim()}>
          ارسال
        </Button>
      </form>
      <div className="px-1 text-[11px] text-muted">Enter ارسال · Shift+Enter خط جدید · هر تغییر مهم قبل از اجرا به تأیید شما می‌رسد.</div>
    </div>
  )
}
