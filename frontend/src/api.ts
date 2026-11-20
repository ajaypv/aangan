import type { AppConfig, Participant, Room, RoomAgentSession, RoomRtcSession, RoomUnchanged, Snapshot, ToolSpec, VoiceSession } from './types'

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
  // Development only: `?mock=1` answers the room endpoints from an in-memory room (src/room/mockRoom.ts). Removed from production builds.
  if (import.meta.env.DEV && path.startsWith('/rooms') && new URLSearchParams(location.search).get('mock') === '1') {
    const { mockRoomRequest } = await import('./room/mockRoom')
    return (await mockRoomRequest(path, body)) as T
  }
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
  /** `multi`: English, Hindi, Telugu and Kannada following what is said. `english`: English only. */
  language: (mode: 'multi' | 'english') => request<AppConfig>('/language', { mode }),
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
  room: {
    create: (title: string, member_id: string | null) => request<Room>('/rooms', { title, member_id }),
    /** `since` is the version the client already has; the server answers `{unchanged: true}` when it is current. */
    get: (id: string, since?: number) => request<Room | RoomUnchanged>(`/rooms/${encodeURIComponent(id)}${since === undefined ? '' : `?since=${since}`}`),
    join: (id: string, who: { member_id: string } | { guest_name: string }) =>
      request<{ participant: Participant; room: Room }>(`/rooms/${encodeURIComponent(id)}/join`, who),
    heartbeat: (id: string, participant_id: string) => request<{ ok: boolean }>(`/rooms/${encodeURIComponent(id)}/heartbeat`, { participant_id }),
    message: (id: string, participant_id: string, text: string, ask?: boolean) =>
      request<Room>(`/rooms/${encodeURIComponent(id)}/message`, ask ? { participant_id, text, ask: true } : { participant_id, text }),
    approve: (id: string, participant_id: string, approve: boolean) => request<Room>(`/rooms/${encodeURIComponent(id)}/approve`, { participant_id, approve }),
    rtc: (id: string, participant_id: string) => request<RoomRtcSession>(`/rooms/${encodeURIComponent(id)}/rtc`, { participant_id }),
    agentStart: (id: string, participant_id: string) => request<RoomAgentSession>(`/rooms/${encodeURIComponent(id)}/agent/start`, { participant_id }),
    agentStop: (id: string) => request<{ stopped: boolean }>(`/rooms/${encodeURIComponent(id)}/agent/stop`, {}),
    resetPlan: (id: string) => request<Room>(`/rooms/${encodeURIComponent(id)}/reset-plan`, {}),
  },
}
