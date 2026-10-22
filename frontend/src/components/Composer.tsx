import { useState } from 'react'

const QUICK = ['وضعیت', 'سایت کند شده', 'دیپلوی ./demo/shop-demo', 'موجودی', 'ری‌استارت']

export function Composer({ onSend, disabled }: { onSend: (t: string) => Promise<void> | void; disabled?: boolean }) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (t: string) => {
    const v = t.trim()
    if (!v || busy) return
    setBusy(true)
    try {
      await onSend(v)
      setText('')
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1.5">
        {QUICK.map((q) => (
          <button key={q} className="chip border border-slate-300 bg-white hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-slate-800" onClick={() => submit(q)} disabled={disabled || busy}>
            {q}
          </button>
        ))}
      </div>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          submit(text)
        }}
      >
        <input className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder="مثلاً: سایت shop-demo کند شده، بررسی کن" disabled={disabled} />
        <button className="btn-primary shrink-0" type="submit" disabled={disabled || busy || !text.trim()}>
          ارسال
        </button>
      </form>
    </div>
  )
}
