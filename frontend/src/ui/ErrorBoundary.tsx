import { Component, type ErrorInfo, type ReactNode } from 'react'

interface State {
  error: Error | null
}

export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Aangan crashed:', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div role="alert" className="grid h-dvh place-items-center bg-bg p-6 text-ink">
        <div className="max-w-sm text-center">
          <h1 className="font-display text-2xl font-extrabold">Something went wrong</h1>
          <p className="mt-2 text-ink-2">Aangan hit an unexpected problem. Reloading usually fixes it.</p>
          <button type="button" onClick={() => location.reload()} className="mt-4 rounded-full bg-btn px-5 py-2.5 font-semibold text-btn-ink">
            Reload
          </button>
        </div>
      </div>
    )
  }
}
