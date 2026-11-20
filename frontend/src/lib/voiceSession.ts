import { useSyncExternalStore } from 'react'
import type { AgentTranscription, AgoraVoiceAI, TranscriptHelperItem, UserTranscription } from 'agora-agent-client-toolkit'
import type { IAgoraRTCClient, IMicrophoneAudioTrack, IRemoteAudioTrack } from 'agora-rtc-sdk-ng'
import type { RTMClient } from 'agora-rtm'
import { api, ApiError } from '@/api'
import type { VoiceSession } from '@/types'

/*
 * Voice session controller, built on Agora's official client pieces exactly as in the proven quickstart:
 * agora-rtc-sdk-ng (audio), agora-rtm (captions, agent state, interrupt) and agora-agent-client-toolkit (AgoraVoiceAI).
 *
 * Order (Agora's documented init order for ConvoAI):
 *   create RTC client -> start the agent on our backend -> RTM login + subscribe -> toolkit init
 *   -> RTC join + publish mic -> toolkit subscribeMessage -> wait for the agent to join.
 * Cleanup is the reverse, and the agent is stopped on our backend FIRST so it can leave the channel cleanly.
 */

export type VoicePhase = 'idle' | 'connecting' | 'waiting-agent' | 'live' | 'ending' | 'error'
export type AgentVoiceState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'silent'
export type StepId = 'backend' | 'captions' | 'channel' | 'mic' | 'agent'
export type StepStatus = 'pending' | 'active' | 'done' | 'failed' | 'skipped'

export const STEP_LABELS: Record<StepId, string> = {
  backend: 'Starting Aangan on the server',
  captions: 'Connecting live captions',
  channel: 'Joining the voice channel',
  mic: 'Opening your microphone',
  agent: 'Waiting for Aangan to join',
}
export const STEP_ORDER: StepId[] = ['backend', 'captions', 'channel', 'mic', 'agent']

export interface VoiceTurn {
  id: string
  who: 'user' | 'agent'
  text: string
  status: 'partial' | 'final' | 'interrupted'
}

export interface VoiceIssue {
  id: number
  source: 'rtc' | 'rtm' | 'agent' | 'backend' | 'mic'
  message: string
  code?: string | number
  at: number
}

export type FailureKind = 'not-configured' | 'no-household' | 'mic-denied' | 'mic-missing' | 'mic-busy' | 'mic-insecure' | 'agent-timeout' | 'agent-left' | 'network' | 'backend' | 'rtc' | 'unknown'

export interface VoiceFailure {
  kind: FailureKind
  title: string
  detail: string
  hints: string[]
  missing?: string[]
}

export interface VoiceState {
  phase: VoicePhase
  memberId: string | null
  session: VoiceSession | null
  steps: Record<StepId, StepStatus>
  agentState: AgentVoiceState | null
  agentJoined: boolean
  rtmReady: boolean
  rtcState: string
  muted: boolean
  turns: VoiceTurn[]
  issues: VoiceIssue[]
  metrics: { name: string; value: number }[]
  error: VoiceFailure | null
}

const idleSteps = (): Record<StepId, StepStatus> => ({ backend: 'pending', captions: 'pending', channel: 'pending', mic: 'pending', agent: 'pending' })

const idleState = (): VoiceState => ({
  phase: 'idle',
  memberId: null,
  session: null,
  steps: idleSteps(),
  agentState: null,
  agentJoined: false,
  rtmReady: false,
  rtcState: 'DISCONNECTED',
  muted: false,
  turns: [],
  issues: [],
  metrics: [],
  error: null,
})

const AGENT_JOIN_TIMEOUT_MS = 20_000
const NETWORK_GRACE_MS = 6_000
const DEFAULT_AGENT_UID = '123456'

const sleep = (ms: number) => new Promise<void>((r) => window.setTimeout(r, ms))
const errCode = (e: unknown): string => (typeof e === 'object' && e !== null && 'code' in e ? String((e as { code: unknown }).code) : '')
const errName = (e: unknown): string => (e instanceof Error || e instanceof DOMException ? e.name : '')
export const errMessage = (e: unknown): string => (e instanceof Error ? e.message : typeof e === 'string' ? e : 'Something went wrong')

function normalizeSpacing(text: string): string {
  return text
    .replace(/([.!?])([A-Za-z])/g, '$1 $2')
    .replace(/,([A-Za-z])/g, ', $1')
    .replace(/\s{2,}/g, ' ')
    .trim()
}

const MIC_HELP = [
  'Click the lock icon in the address bar, open Site settings, and set Microphone to Allow.',
  'Reload this page and tap Try again.',
  'On a phone, also check that the browser itself is allowed to use the microphone in the system settings.',
]

export function failureFor(e: unknown, stage: 'start' | 'channel' | 'mic'): VoiceFailure {
  if (e instanceof ApiError) {
    if (e.status === 503) {
      const missing = e.missing
      return {
        kind: 'not-configured',
        title: 'Voice is not connected yet',
        detail: missing.length ? `Missing: ${missing.join(', ')}.` : 'The server says voice is not configured.',
        hints: ['Add the missing values to backend/.env and restart the backend.', 'Text chat works without voice.'],
        missing,
      }
    }
    if (e.status === 409 && (e.detail as { error?: string } | undefined)?.error === 'no_household') {
      return {
        kind: 'no-household',
        title: 'Set up your family first',
        detail: 'Aangan does not know anyone in this household yet, so there is nobody to talk to.',
        hints: ['Create your profile, and Aangan will be ready.'],
      }
    }
    if (e.status === 0) {
      return { kind: 'network', title: 'Cannot reach the Aangan server', detail: e.message, hints: ['Check your connection and that the backend is running, then try again.'] }
    }
    return {
      kind: 'backend',
      title: 'The server could not start the voice agent',
      detail: e.message,
      hints: ['If it mentions Agora, check the Agora keys and that Conversational AI is enabled for the project.', 'Look at the backend log for the full error.'],
    }
  }
  if (stage === 'mic') {
    const code = errCode(e)
    const name = errName(e)
    if (code === 'PERMISSION_DENIED' || name === 'NotAllowedError') {
      return { kind: 'mic-denied', title: 'Microphone access was blocked', detail: 'Aangan needs your microphone to hear you.', hints: MIC_HELP }
    }
    if (code === 'DEVICE_NOT_FOUND' || name === 'NotFoundError') {
      return { kind: 'mic-missing', title: 'No microphone found', detail: 'This device did not report a microphone.', hints: ['Plug in or enable a microphone, then tap Try again.'] }
    }
    if (code === 'NOT_READABLE' || name === 'NotReadableError') {
      return { kind: 'mic-busy', title: 'The microphone is busy', detail: 'Another app or tab is using it.', hints: ['Close other apps or tabs that use the microphone, then tap Try again.'] }
    }
  }
  if (stage === 'channel') {
    return {
      kind: 'rtc',
      title: 'Could not join the voice channel',
      detail: errMessage(e),
      hints: ['Check your internet connection and try again.', 'If it keeps failing, the Agora token may have been rejected: check the app ID and certificate.'],
    }
  }
  return { kind: 'unknown', title: 'Voice stopped working', detail: errMessage(e), hints: ['Tap Try again. If it repeats, open Connection details for more information.'] }
}

class VoiceController {
  private state: VoiceState = idleState()
  private listeners = new Set<() => void>()
  private gen = 0
  private session: VoiceSession | null = null
  private rtc: IAgoraRTCClient | null = null
  private rtm: RTMClient | null = null
  private mic: IMicrophoneAudioTrack | null = null
  private agentAudio: IRemoteAudioTrack | null = null
  private ai: AgoraVoiceAI | null = null
  private joinTimer: number | undefined
  private netTimer: number | undefined
  private issueSeq = 1

  subscribe = (fn: () => void) => {
    this.listeners.add(fn)
    return () => {
      this.listeners.delete(fn)
    }
  }

  getState = () => this.state

  /** Live audio levels (0 to 1) for the waveform; cheap to poll every frame. */
  getLevels(): { mic: number; agent: number } {
    let mic = 0
    let agent = 0
    try {
      if (this.mic && !this.state.muted) mic = this.mic.getVolumeLevel()
    } catch {
      // Track already closed.
    }
    try {
      if (this.agentAudio) agent = this.agentAudio.getVolumeLevel()
    } catch {
      // Track already closed.
    }
    return { mic, agent }
  }

  private set(patch: Partial<VoiceState>) {
    this.state = { ...this.state, ...patch }
    for (const l of this.listeners) l()
  }

  private setStep(id: StepId, status: StepStatus) {
    this.set({ steps: { ...this.state.steps, [id]: status } })
  }

  private addIssue(source: VoiceIssue['source'], message: string, code?: string | number) {
    const at = Date.now()
    const dupe = this.state.issues.some((i) => i.message === message && i.source === source && at - i.at < 1500)
    if (dupe) return
    this.set({ issues: [{ id: this.issueSeq++, source, message, code, at }, ...this.state.issues].slice(0, 8) })
  }

  private agentUid() {
    return this.session?.agent_uid ?? DEFAULT_AGENT_UID
  }

  private clearTimers() {
    window.clearTimeout(this.joinTimer)
    window.clearTimeout(this.netTimer)
    this.joinTimer = undefined
    this.netTimer = undefined
  }

  private markAgentJoined() {
    if (this.state.agentJoined) return
    this.set({ agentJoined: true })
    if (this.state.phase === 'waiting-agent') this.goLive()
  }

  private goLive() {
    window.clearTimeout(this.joinTimer)
    this.joinTimer = undefined
    this.setStep('agent', 'done')
    this.set({ phase: 'live', agentState: this.state.agentState ?? 'listening' })
  }

  async start(memberId: string): Promise<void> {
    if (this.state.phase !== 'idle' && this.state.phase !== 'error') return
    const gen = ++this.gen
    this.session = null
    this.set({ ...idleState(), phase: 'connecting', memberId, steps: { ...idleSteps(), backend: 'active' } })

    let stage: 'start' | 'channel' | 'mic' = 'start'
    try {
      // 0. Create the RTC client first (Agora: initialise RTC, but do not join yet).
      const AgoraRTC = (await import('agora-rtc-sdk-ng')).default
      if (gen !== this.gen) return
      try {
        ;(AgoraRTC as unknown as { setParameter?: (k: string, v: unknown) => void }).setParameter?.('ENABLE_AUDIO_PTS', true)
      } catch {
        // Only needed for word-level timing.
      }
      const client = AgoraRTC.createClient({ mode: 'rtc', codec: 'vp8' })
      this.rtc = client
      this.bindRtc(client, gen)

      // 1. Ask our backend to start the agent and mint tokens. The agent waits for us to join before greeting.
      const session = await api.agentStart(memberId)
      if (gen !== this.gen) {
        await api.agentStop().catch(() => {})
        return
      }
      this.session = session
      this.set({ session })
      this.setStep('backend', 'done')

      // 2. RTM login + subscribe, then the toolkit, before we join so the greeting transcript is not missed.
      this.setStep('captions', 'active')
      const tk = await import('agora-agent-client-toolkit')
      const rtmOk = await this.connectRtm(session, gen)
      if (gen !== this.gen) return
      this.set({ rtmReady: rtmOk })
      this.setStep('captions', rtmOk ? 'done' : 'skipped')

      const ai = await tk.AgoraVoiceAI.init({
        rtcEngine: client,
        rtmEngine: rtmOk && this.rtm ? this.rtm : undefined,
        renderMode: tk.TranscriptHelperMode.TEXT,
        enableLog: false,
      })
      if (gen !== this.gen) {
        ai.destroy()
        return
      }
      this.ai = ai
      this.bindToolkit(ai, tk, session)

      // 3. Join the RTC channel and publish the microphone.
      stage = 'channel'
      this.setStep('channel', 'active')
      await client.join(session.app_id, session.channel, session.token, session.uid)
      if (gen !== this.gen) return
      this.setStep('channel', 'done')

      stage = 'mic'
      this.setStep('mic', 'active')
      if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
        throw Object.assign(new Error('Insecure page'), { name: 'InsecureContext' })
      }
      const mic = await AgoraRTC.createMicrophoneAudioTrack({ AEC: true, ANS: true, AGC: true })
      if (gen !== this.gen) {
        mic.close()
        return
      }
      this.mic = mic
      await client.publish([mic])
      if (gen !== this.gen) return
      this.setStep('mic', 'done')

      // 4. Start receiving transcripts and agent state (after join, per the toolkit docs).
      ai.subscribeMessage(session.channel)

      // 5. Wait for the agent to appear in the channel.
      if (client.remoteUsers.some((u) => String(u.uid) === this.agentUid())) this.set({ agentJoined: true })
      this.setStep('agent', 'active')
      if (this.state.agentJoined) {
        this.set({ phase: 'live', agentState: 'listening' })
        this.setStep('agent', 'done')
      } else {
        this.set({ phase: 'waiting-agent' })
        this.joinTimer = window.setTimeout(() => {
          if (gen !== this.gen || this.state.agentJoined) return
          void this.fail({
            kind: 'agent-timeout',
            title: 'Aangan did not join the call',
            detail: 'The voice agent had not joined after 20 seconds.',
            hints: [
              'Check that the backend and the public tunnel are both running.',
              'The tunnel address (PUBLIC_BASE_URL) changes each time the tunnel restarts; it must match the backend .env.',
              'Tap Try again to start a fresh call.',
            ],
          })
        }, AGENT_JOIN_TIMEOUT_MS)
      }
    } catch (e) {
      if (gen !== this.gen) return
      const insecure = errName(e) === 'InsecureContext'
      const failure = insecure
        ? { kind: 'mic-insecure' as const, title: 'Microphone needs a secure page', detail: 'Browsers only allow the microphone on https pages or on localhost.', hints: ['Open Aangan from its https address or from localhost.'] }
        : failureFor(e, stage)
      await this.fail(failure, stage !== 'start' || !(e instanceof ApiError))
    }
  }

  private bindRtc(client: IAgoraRTCClient, gen: number) {
    client.on('user-published', async (user, mediaType) => {
      try {
        await client.subscribe(user, mediaType)
        if (mediaType === 'audio') {
          user.audioTrack?.play()
          if (String(user.uid) === this.agentUid()) {
            this.agentAudio = user.audioTrack ?? null
            this.markAgentJoined()
          }
        }
      } catch (e) {
        this.addIssue('rtc', `Could not play Aangan's audio: ${errMessage(e)}`, errCode(e))
      }
    })
    client.on('user-joined', (user) => {
      if (String(user.uid) === this.agentUid()) this.markAgentJoined()
    })
    client.on('user-left', (user) => {
      if (String(user.uid) !== this.agentUid() || gen !== this.gen) return
      if (this.state.phase === 'live' || this.state.phase === 'waiting-agent') {
        void this.fail({
          kind: 'agent-left',
          title: 'Aangan left the call',
          detail: 'The voice agent disconnected. It leaves on its own after a stretch of silence, or if the voice service had a problem.',
          hints: ['Tap Try again to start a new call.'],
        })
      }
    })
    client.on('connection-state-change', (cur) => {
      if (gen !== this.gen) return
      this.set({ rtcState: cur })
      if (cur === 'CONNECTED') {
        window.clearTimeout(this.netTimer)
        this.netTimer = undefined
        return
      }
      if (cur === 'RECONNECTING') this.addIssue('rtc', 'The connection was interrupted. Reconnecting…')
      const active = this.state.phase === 'live' || this.state.phase === 'waiting-agent' || this.state.phase === 'connecting'
      if ((cur === 'DISCONNECTED' || cur === 'RECONNECTING') && active && this.netTimer === undefined) {
        this.netTimer = window.setTimeout(() => {
          if (gen !== this.gen) return
          void this.fail({
            kind: 'network',
            title: 'The connection dropped',
            detail: navigator.onLine ? 'The voice connection could not be restored.' : 'Your device went offline.',
            hints: ['Check your internet connection, then tap Try again.'],
          })
        }, NETWORK_GRACE_MS)
      }
    })
    client.on('token-privilege-will-expire', () => {
      this.addIssue('rtc', 'This call is about to reach its time limit. Start a new call to keep talking.')
    })
    client.on('exception', (e) => {
      this.addIssue('rtc', `Audio warning: ${e.msg}`, e.code)
    })
  }

  private async connectRtm(session: VoiceSession, gen: number): Promise<boolean> {
    const { default: AgoraRTM } = await import('agora-rtm')
    // The RTM login identity must equal the identity the RTM token was minted for.
    const userId = session.rtm_user_id ?? String(session.uid)
    const token = session.rtm_token ?? session.token
    let lastError: unknown
    for (let attempt = 1; attempt <= 3; attempt++) {
      if (gen !== this.gen) return false
      const rtm = new AgoraRTM.RTM(session.app_id, userId)
      try {
        await rtm.login({ token })
        await rtm.subscribe(session.channel)
        if (gen !== this.gen) {
          await rtm.logout().catch(() => {})
          return false
        }
        this.rtm = rtm
        return true
      } catch (e) {
        lastError = e
        await rtm.logout().catch(() => {})
        // Agora notes RTM can lag behind project settings; retry briefly before giving up.
        if (attempt < 3) await sleep(1200)
      }
    }
    this.addIssue('rtm', `Live captions are unavailable (${errMessage(lastError)}). Voice still works, but Aangan's state and the interrupt button need captions.`, errCode(lastError))
    return false
  }

  private bindToolkit(ai: AgoraVoiceAI, tk: typeof import('agora-agent-client-toolkit'), session: VoiceSession) {
    const agentUid = session.agent_uid ?? DEFAULT_AGENT_UID
    ai.on(tk.AgoraVoiceAIEvents.TRANSCRIPT_UPDATED, (items) => {
      this.set({ turns: this.mapTurns(items, agentUid, tk) })
    })
    ai.on(tk.AgoraVoiceAIEvents.AGENT_STATE_CHANGED, (_agent, event) => {
      this.set({ agentState: event.state as AgentVoiceState })
      this.markAgentJoined()
    })
    ai.on(tk.AgoraVoiceAIEvents.AGENT_METRICS, (_agent, m) => {
      this.set({ metrics: [...this.state.metrics, { name: `${m.type} ${m.name}`, value: m.value }].slice(-6) })
    })
    ai.on(tk.AgoraVoiceAIEvents.AGENT_ERROR, (_agent, e) => {
      this.addIssue('agent', `${e.type}: ${e.message}`, e.code)
    })
    ai.on(tk.AgoraVoiceAIEvents.MESSAGE_ERROR, (_agent, e) => {
      this.addIssue('rtm', e.message, e.code)
    })
  }

  private mapTurns(
    items: TranscriptHelperItem<Partial<UserTranscription | AgentTranscription>>[],
    agentUid: string,
    tk: typeof import('agora-agent-client-toolkit'),
  ): VoiceTurn[] {
    return items
      .map((item) => ({
        id: `${item.turn_id}:${item.uid}:${item.stream_id}`,
        who: (item.uid === agentUid ? 'agent' : 'user') as VoiceTurn['who'],
        text: normalizeSpacing(typeof item.text === 'string' ? item.text : ''),
        status: (item.status === tk.TurnStatus.IN_PROGRESS ? 'partial' : item.status === tk.TurnStatus.INTERRUPTED ? 'interrupted' : 'final') as VoiceTurn['status'],
      }))
      .filter((t) => t.text)
  }

  async stop(): Promise<void> {
    const phase = this.state.phase
    if (phase === 'idle' || phase === 'ending') return
    if (phase === 'error') {
      this.set(idleState())
      return
    }
    const gen = ++this.gen
    this.clearTimers()
    this.set({ phase: 'ending' })
    // Agora: stop the agent from the server before leaving the channel, so it can exit cleanly.
    try {
      await api.agentStop()
    } catch (e) {
      this.addIssue('backend', `Could not confirm the agent stopped: ${errMessage(e)}`)
    }
    await this.release()
    if (gen === this.gen) this.set(idleState())
  }

  private async fail(failure: VoiceFailure, stopAgent = true): Promise<void> {
    this.clearTimers()
    const gen = ++this.gen
    const steps = { ...this.state.steps }
    for (const id of STEP_ORDER) if (steps[id] === 'active') steps[id] = 'failed'
    this.set({ phase: 'error', error: failure, steps, agentState: null })
    if (stopAgent) {
      try {
        await api.agentStop()
      } catch {
        // The backend also ends idle agents on its own.
      }
    }
    if (gen !== this.gen) return
    await this.release()
    if (gen === this.gen) this.set({ agentJoined: false, rtmReady: false, rtcState: 'DISCONNECTED' })
  }

  /** Tear everything down in Agora's documented order: toolkit, mic, RTC, then RTM. */
  private async release(): Promise<void> {
    this.clearTimers()
    const { ai, mic, rtc, rtm, session } = this
    this.ai = null
    this.mic = null
    this.rtc = null
    this.rtm = null
    this.agentAudio = null
    try {
      ai?.unsubscribe()
      ai?.destroy()
    } catch {
      // Already destroyed.
    }
    try {
      mic?.stop()
      mic?.close()
    } catch {
      // Already closed.
    }
    try {
      rtc?.removeAllListeners()
      await rtc?.leave()
    } catch {
      // Already left.
    }
    try {
      if (session) await rtm?.unsubscribe(session.channel)
    } catch {
      // Not subscribed.
    }
    try {
      await rtm?.logout()
    } catch {
      // Already logged out.
    }
  }

  async toggleMute(): Promise<void> {
    if (!this.mic) return
    const next = !this.state.muted
    try {
      await this.mic.setEnabled(!next)
      this.set({ muted: next })
    } catch (e) {
      this.addIssue('mic', `Could not change the microphone: ${errMessage(e)}`)
    }
  }

  /** Cut Aangan off mid-sentence. Needs the RTM captions connection. Returns an error text, or null on success. */
  async interrupt(): Promise<string | null> {
    if (!this.ai || !this.state.rtmReady) return 'Interrupt needs the live captions connection, which is not available.'
    try {
      await this.ai.interrupt(this.agentUid())
      return null
    } catch (e) {
      const message = `Could not interrupt: ${errMessage(e)}`
      this.addIssue('rtm', message)
      return message
    }
  }

  dismissError() {
    if (this.state.phase === 'error') this.set(idleState())
  }

  /** Stop billing when the page goes away: a beacon survives unload, unlike a normal fetch. */
  beacon() {
    if (this.state.phase === 'idle' || this.state.phase === 'error') return
    try {
      navigator.sendBeacon('/api/agent/stop', new Blob(['{}'], { type: 'application/json' }))
    } catch {
      // Nothing else can be done during unload.
    }
  }

  /** Dev only: render any phase without a real call. */
  debugSet(patch: Partial<VoiceState>) {
    this.set(patch)
  }
}

export const voice = new VoiceController()

if (typeof window !== 'undefined') {
  window.addEventListener('pagehide', () => voice.beacon())
  if (import.meta.env.DEV) (window as unknown as { __voice: VoiceController }).__voice = voice
}

export function useVoiceState(): VoiceState {
  return useSyncExternalStore(voice.subscribe, voice.getState, voice.getState)
}

export const isVoiceActive = (v: VoiceState) => v.phase === 'connecting' || v.phase === 'waiting-agent' || v.phase === 'live' || v.phase === 'ending'
