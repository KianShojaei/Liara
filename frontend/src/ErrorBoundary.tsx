import { Component, type ErrorInfo, type ReactNode } from 'react'

interface State {
  error: Error | null
}

/** Never leave the user with a blank page: show the error and a reset button instead. */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('UI crashed:', error, info.componentStack)
  }

  reset = () => {
    try {
      localStorage.removeItem('copilot.session')
    } catch {
      /* ignore */
    }
    location.reload()
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div dir="rtl" className="mx-auto mt-10 max-w-xl rounded-2xl border border-rose-300 bg-white p-6 text-slate-900 shadow">
        <h1 className="text-lg font-bold">رابط کاربری دچار خطا شد</h1>
        <p className="mt-2 text-sm">این خطا را برای توسعه‌دهنده بفرستید:</p>
        <pre className="mono mt-2 max-h-60 overflow-auto rounded-lg bg-slate-100 p-3 text-xs">{this.state.error.message}\n{this.state.error.stack}</pre>
        <button className="btn-primary mt-4" onClick={this.reset}>شروع دوباره</button>
      </div>
    )
  }
}
