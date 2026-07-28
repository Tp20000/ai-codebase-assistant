/**
 * Error Boundary — Catches React render errors and shows friendly UI.
 * All errors are visible in UI — never only in console.
 */

import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertTriangle, RefreshCw, Home } from 'lucide-react'

interface Props {
  children: ReactNode
  fallback?: ReactNode
  componentName?: string
}

interface State {
  hasError: boolean
  error: Error | null
  errorInfo: ErrorInfo | null
}

class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null, errorInfo: null }
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error(
      `[ErrorBoundary] Error in ${this.props.componentName ?? 'component'}:`,
      error,
      errorInfo,
    )
    this.setState({ errorInfo })
  }

  handleReset = (): void => {
    this.setState({ hasError: false, error: null, errorInfo: null })
  }

  render(): ReactNode {
    if (!this.state.hasError) {
      return this.props.children
    }

    if (this.props.fallback) {
      return this.props.fallback
    }

    const isDev = import.meta.env.DEV

    return (
      <div className="min-h-screen bg-dark-bg flex items-center justify-center p-6">
        <div className="max-w-lg w-full glass-card p-8 text-center">
          <div className="flex justify-center mb-6">
            <div className="w-16 h-16 rounded-full bg-red-500/10 flex items-center justify-center">
              <AlertTriangle className="w-8 h-8 text-red-400" />
            </div>
          </div>

          <h2 className="text-xl font-semibold text-gray-100 mb-2">
            Something went wrong
          </h2>

          {this.props.componentName && (
            <p className="text-sm text-gray-500 mb-4">
              Error in: <code className="text-red-400">{this.props.componentName}</code>
            </p>
          )}

          {this.state.error && (
            <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 mb-6 text-left">
              <p className="text-sm font-mono text-red-300 break-all">
                {this.state.error.message}
              </p>
            </div>
          )}

          {isDev && this.state.errorInfo && (
            <details className="text-left mb-6">
              <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-300 mb-2">
                Show stack trace (dev only)
              </summary>
              <pre className="text-xs text-gray-400 bg-dark-surface p-3 rounded overflow-auto max-h-40">
                {this.state.errorInfo.componentStack}
              </pre>
            </details>
          )}

          <div className="flex gap-3 justify-center">
            <button onClick={this.handleReset} className="btn-primary">
              <RefreshCw className="w-4 h-4" />
              Try Again
            </button>
            <button
              onClick={() => { window.location.href = '/' }}
              className="btn-ghost"
            >
              <Home className="w-4 h-4" />
              Go Home
            </button>
          </div>
        </div>
      </div>
    )
  }
}

export default ErrorBoundary
