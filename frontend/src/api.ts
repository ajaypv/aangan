import type { AppConfig, Snapshot, ToolSpec, VoiceSession } from './types'

export class ApiError extends Error {
  status: number
  detail: unknown
  constructor(status: number, message: string, detail?: unknown) {
    super(message)
    this.status = status
    this.detail = detail
  }
  /** The env var names the backend says are missing, when it answered 503 not_configured. */
  get missing(): string[] {
    const d = this.detail as { missing?: string[] } | undefined
    return Array.isArray(d?.missing) ? d.missing : []
  }
  /** The backend's error code (for example `no_household` or `not_configured`), when it sent one. */
  get code(): string | undefined {
    const d = this.detail as { error?: unknown } | undefined
    return typeof d?.error === 'string' ? d.error : undefined
  }
}

/** The plain-language text a failed response carries: a string detail, or `detail.message` from an error object. */
function messageFrom(detail: unknown, status: number): string {
  if (typeof detail === 'string') return detail
  const m = (detail as { message?: unknown } | undefined)?.message
  if (typeof m === 'string' && m) return m
  return `Request failed (${status})`
}

async function request<T>(path: string, body?: unknown): Promise<T> {
  let res: Response
  try {
    res = await fetch(`/api${path}`, {
      method: body === undefined ? 'GET' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, 'Cannot reach the Aangan server. Check your connection and that the backend is running.')
  }
  if (!res.ok) {
    let detail: unknown
    try {
      detail = (await res.json()).detail
    } catch {
      detail = undefined
    }
    throw new ApiError(res.status, messageFrom(detail, res.status), detail)
  }
  return (await res.json()) as T
}

export const api = {
  state: () => request<Snapshot>('/state'),
  config: () => request<AppConfig>('/config'),
  tools: () => request<ToolSpec[]>('/tools'),
  converse: (member_id: string, message: string) => request<{ reply: string; state: Snapshot }>('/converse', { member_id, message }),
  trigger: (agent: string, name: string) => request<{ reply: string | null; state: Snapshot }>(`/trigger/${agent}/${name}`, {}),
  tool: (agent: string, tool: string, args: Record<string, unknown>) =>
    request<{ status: 'ok' | 'error'; result: Record<string, unknown>; state: Snapshot }>(`/tool/${agent}/${tool}`, { args }),
  chaos: (enabled: boolean) => request<Snapshot>('/chaos', { enabled }),
  /** Back to the starting point of the current mode (the demo family while in demo mode, an empty household otherwise). */
  reset: () => request<Snapshot>('/reset', {}),
  household: {
    /** Load the built-in example family. */
    demo: () => request<Snapshot>('/household/demo', {}),
    /** Empty the household completely. */
    reset: () => request<Snapshot>('/household/reset', {}),
  },
  agentStart: (member_id: string) => request<VoiceSession>('/agent/start', { member_id }),
  agentStop: () => request<{ stopped: boolean }>('/agent/stop', {}),
}
