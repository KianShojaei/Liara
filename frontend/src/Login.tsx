import { useState, type FormEvent } from 'react'
import { api } from './api'
import { LockIcon } from './components/icons'

/** Shown when the deployment has COPILOT_UI_PASSWORD set and the session cookie is missing. */
export function Login({ onDone }: { onDone: () => void }) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api.login(password)
      onDone()
    } catch (err) {
      setError((err as Error).message || 'رمز اشتباه است')
    } finally {
      setBusy(false)
    }
  }
  return (
    <div className="grid min-h-screen place-items-center px-4">
      <form onSubmit={submit} className="card w-full max-w-sm space-y-4">
        <div className="flex items-center gap-2">
          <span className="grid h-9 w-9 place-items-center rounded-xl bg-emerald-600/15 text-emerald-500"><LockIcon size={18} /></span>
          <div>
            <h1 className="text-base font-semibold">ورود به Liara Ops Copilot</h1>
            <p className="text-xs text-muted">این نسخه عمومی است و با رمز محافظت می‌شود.</p>
          </div>
        </div>
        <label className="block text-sm">
          رمز ورود
          <input id="ui-password" className="input mt-1" type="password" autoFocus value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        {error && <p className="text-sm text-rose-500">{error}</p>}
        <button type="submit" className="btn-primary w-full" disabled={busy || !password}>{busy ? 'در حال ورود…' : 'ورود'}</button>
      </form>
    </div>
  )
}
