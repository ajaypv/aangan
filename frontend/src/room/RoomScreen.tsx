import { ChevronDown, ChevronUp, CloudOff, MessageSquare, Users, WifiOff } from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { api, ApiError } from '@/api'
import { useMediaQuery } from '@/lib/useMediaQuery'
import { cn } from '@/lib/utils'
import { useApp } from '@/state/AppState'
import { useMe } from '@/state/me'
import type { Participant, Room } from '@/types'
import { Banner, Button, EmptyState, Field, inputClass, ScreenSkeleton } from '@/ui/primitives'
import { Conversation } from './Conversation'
import { QuestionsCard } from './board/ListCards'
import { PandaCompanion } from './PandaCompanion'
import { PlanBoard } from './PlanBoard'
import { RoomHeader } from './RoomHeader'
import { leaveRoomRoute, loadIdentity, saveIdentity } from './roomRoute'
import { BoardFlashProvider } from './useBoardFlash'
import { useRoom } from './useRoom'
import { useRoomRtc } from './useRoomRtc'
import { anyCameraOn, CallControls, VideoStrip } from './VideoStrip'
import './room.css'

type Entry =
  | { phase: 'loading' }
  | { phase: 'missing' }
  | { phase: 'error'; message: string }
  | { phase: 'name'; room: Room }
  | { phase: 'ready'; room: Room; participant: Participant }

const isRoom = (r: unknown): r is Room => typeof r === 'object' && r !== null && 'plan' in r

/**
 * The room at `?room=<id>`. It first finds out who this device is in the room: a person with a profile joins as themselves
 * (member_id), someone returning uses the participant remembered for this room, anyone else is asked for a name and joins as a guest.
 */
export function RoomScreen({ roomId }: { roomId: string }) {
  const { setTab } = useApp()
  const { me: memberId } = useMe()
  const [entry, setEntry] = useState<Entry>({ phase: 'loading' })
  const [attempt, setAttempt] = useState(0)

  const goHome = useCallback(() => {
    leaveRoomRoute()
    setTab('home')
  }, [setTab])

  useEffect(() => {
    let alive = true
    setEntry({ phase: 'loading' })
    void (async () => {
      try {
        const room = await api.room.get(roomId)
        if (!alive) return
        if (!isRoom(room)) throw new ApiError(500, 'Unexpected answer from the server')
        const remembered = loadIdentity(roomId)
        const known = remembered && room.participants.find((p) => p.id === remembered.participant_id && (!memberId || p.member_id === memberId))
        if (known) return setEntry({ phase: 'ready', room, participant: known })
        if (memberId) {
          try {
            const joined = await api.room.join(roomId, { member_id: memberId })
            if (!alive) return
            saveIdentity(roomId, { participant_id: joined.participant.id })
            return setEntry({ phase: 'ready', room: joined.room, participant: joined.participant })
          } catch (e) {
            if (e instanceof ApiError && e.status === 404 && /unknown room/i.test(e.message)) throw e
            // This person is not known to the room's server: carry on as a guest.
          }
        }
        setEntry({ phase: 'name', room })
      } catch (e) {
        if (!alive) return
        if (e instanceof ApiError && e.status === 404) setEntry({ phase: 'missing' })
        else setEntry({ phase: 'error', message: e instanceof Error ? e.message : 'Could not open the room' })
      }
    })()
    return () => {
      alive = false
    }
  }, [roomId, memberId, attempt])

  if (entry.phase === 'loading') {
    return (
      <div className="h-dvh overflow-y-auto bg-bg text-ink">
        <ScreenSkeleton />
      </div>
    )
  }
  if (entry.phase === 'missing' || entry.phase === 'error') {
    return (
      <div className="h-dvh overflow-y-auto bg-bg p-6 text-ink">
        <div className="mx-auto max-w-md">
          <EmptyState
            icon={<CloudOff className="size-6" aria-hidden="true" />}
            title={entry.phase === 'missing' ? 'This room does not exist' : 'Could not open the room'}
            action={
              <div className="flex gap-2">
                {entry.phase === 'error' && <Button onClick={() => setAttempt((n) => n + 1)}>Try again</Button>}
                <Button variant="secondary" onClick={goHome}>
                  Back to Home
                </Button>
              </div>
            }
          >
            <p>{entry.phase === 'missing' ? 'The invite link may be old or mistyped. Ask the host to send it again.' : entry.message}</p>
          </EmptyState>
        </div>
      </div>
    )
  }
  if (entry.phase === 'name') {
    return (
      <NameGate
        room={entry.room}
        onJoined={(participant, room) => {
          saveIdentity(roomId, { participant_id: participant.id, guest_name: participant.name })
          setEntry({ phase: 'ready', room, participant })
        }}
        onBack={goHome}
      />
    )
  }
  return <RoomView roomId={roomId} initial={entry.room} participant={entry.participant} onBack={goHome} onLeave={() => (saveIdentity(roomId, null), goHome())} />
}

/** A guest is asked for one thing: a name. */
function NameGate({ room, onJoined, onBack }: { room: Room; onJoined: (p: Participant, r: Room) => void; onBack: () => void }) {
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const host = room.participants.find((p) => p.id === room.host_participant_id)

  const join = async (e: FormEvent) => {
    e.preventDefault()
    const guest_name = name.trim()
    if (!guest_name) return
    setBusy(true)
    setError(null)
    try {
      const res = await api.room.join(room.id, { guest_name })
      onJoined(res.participant, res.room)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not join the room')
      setBusy(false)
    }
  }

  return (
    <div className="h-dvh overflow-y-auto bg-bg p-4 text-ink">
      <form onSubmit={join} className="mx-auto mt-[8vh] max-w-sm rounded-xl border border-line bg-surface p-6 shadow-xs">
        <span className="mb-3 grid size-12 place-items-center rounded-full bg-brand-soft text-brand-text" aria-hidden="true">
          <Users className="size-6" />
        </span>
        <h1 className="t-page">Join {room.title}</h1>
        <p className="t-secondary mt-1">{host ? `${host.name} invited you to plan together with Aangan.` : 'You are invited to plan together with Aangan.'} What should everyone call you?</p>
        <div className="mt-4">
          <Field label="Your name">
            <input value={name} onChange={(e) => setName(e.target.value)} className={inputClass} autoComplete="given-name" maxLength={40} autoFocus enterKeyHint="go" />
          </Field>
        </div>
        {error && (
          <p role="alert" className="mt-2 text-sm font-medium text-[var(--rw-text-danger)]">
            {error}
          </p>
        )}
        <div className="mt-4 flex gap-2">
          <Button type="submit" loading={busy} disabled={!name.trim()} className="flex-1">
            Join room
          </Button>
          <Button variant="secondary" onClick={onBack}>
            Not now
          </Button>
        </div>
      </form>
    </div>
  )
}

type PanelTab = 'plan' | 'chat'

function RoomView({ roomId, initial, participant, onBack, onLeave }: { roomId: string; initial: Room; participant: Participant; onBack: () => void; onLeave: () => void }) {
  const { room, me, messages, reconnecting, send, approve, refresh } = useRoom(roomId, participant.id, initial)
  const rtc = useRoomRtc(roomId, participant.id)
  const wide = useMediaQuery('(min-width: 1024px)')
  const [tab, setTab] = useState<PanelTab>('plan')
  // On a wide screen the conversation is open from the start: the column beside the plan would otherwise sit empty behind a button.
  const [chatExpanded, setChatExpanded] = useState(() => typeof window !== 'undefined' && window.matchMedia('(min-width: 1024px)').matches)
  const [seenId, setSeenId] = useState(() => Math.max(0, ...initial.messages.map((m) => m.id)))
  const [planDot, setPlanDot] = useState(false)
  const [agentBusy, setAgentBusy] = useState(false)
  const [agentError, setAgentError] = useState<string | null>(null)
  const [agentUid, setAgentUid] = useState<string | null>(null)
  const micRef = useRef(rtc)
  micRef.current = rtc

  const chatVisible = wide ? chatExpanded : tab === 'chat'
  const lastId = Math.max(0, ...room.messages.map((m) => m.id))
  useEffect(() => {
    if (chatVisible) setSeenId(lastId)
  }, [chatVisible, lastId])
  useEffect(() => {
    if (wide || tab === 'plan') setPlanDot(false)
  }, [wide, tab])
  const unread = chatVisible ? 0 : room.messages.filter((m) => m.id > seenId && m.participant_id !== participant.id).length

  const summon = async () => {
    setAgentBusy(true)
    setAgentError(null)
    try {
      const res = await api.room.agentStart(roomId, participant.id)
      setAgentUid(String(res.agent_uid))
      await refresh()
      // Aangan can only hear you with a microphone on: this tap is the permission moment.
      if (!micRef.current.micOn) void micRef.current.toggleMic()
    } catch (e) {
      setAgentError(e instanceof Error ? e.message : 'Could not start the voice assistant')
    } finally {
      setAgentBusy(false)
    }
  }
  const dismiss = async () => {
    setAgentBusy(true)
    setAgentError(null)
    try {
      await api.room.agentStop(roomId)
      setAgentUid(null)
      await refresh()
    } catch (e) {
      setAgentError(e instanceof Error ? e.message : 'Could not stop the voice assistant')
    } finally {
      setAgentBusy(false)
    }
  }

  const agentUidNow = String(room.agent.voice_session?.agent_uid ?? agentUid ?? '123456')
  const sendMessage = (text: string, ask: boolean) => send(text, ask)

  return (
    <div className="flex h-dvh flex-col bg-bg text-ink">
      <RoomHeader room={room} me={me} onBack={onBack} onLeave={onLeave} />
      {reconnecting && (
        <Banner tone="warning" icon={<WifiOff className="size-4" aria-hidden="true" />}>
          Reconnecting… your messages will go through once the connection is back.
        </Banner>
      )}

      <BoardFlashProvider room={room} onPlanChanged={() => setPlanDot(true)}>
        <main id="main" data-chat-open={chatExpanded} className="room-workspace flex min-h-0 flex-1 flex-col">
          {/* The plan: its own scroll. On phones it is one of two tabs. */}
          <section
            id="room-plan-panel"
            role={wide ? undefined : 'tabpanel'}
            aria-label="Plan"
            aria-labelledby={wide ? undefined : 'room-tab-plan'}
            className={cn('room-plan-panel order-3 min-h-0 min-w-0 flex-1 overflow-y-auto overscroll-contain', tab === 'plan' ? 'block' : 'hidden', 'lg:order-none lg:block')}
          >
            <PlanBoard room={room} me={me} onDecide={approve} />
          </section>

          {/* The discussion: video strip on top, then the conversation. `contents` lets the phone order these with the tabs. */}
          <div className="room-discussion contents lg:flex lg:min-h-0 lg:min-w-0 lg:flex-col lg:border-l lg:border-line">
            <div className="order-1 shrink-0 lg:order-none">
              <VideoStrip room={room} me={me} rtc={rtc} />
              <PandaCompanion
                room={room}
                rtc={rtc}
                agentUid={agentUidNow}
                connecting={agentBusy && !room.agent.live}
                controls={anyCameraOn(rtc) ? null : <CallControls rtc={rtc} />}
              />
              {wide && room.plan.open_questions.some((question) => !question.resolved) && (
                <div className="room-discussion-questions"><QuestionsCard room={room} /></div>
              )}
            </div>

            <button
              type="button"
              className="room-chat-toggle"
              aria-expanded={chatExpanded}
              aria-controls="room-conversation-history"
              onClick={() => setChatExpanded((open) => !open)}
            >
              <MessageSquare className="size-4" aria-hidden="true" />
              <span>{chatExpanded ? 'Collapse conversation' : 'Expand conversation'}</span>
              {!chatExpanded && unread > 0 && <span className="room-unread" aria-label={`${unread} unread ${unread === 1 ? 'message' : 'messages'}`}>{unread}</span>}
              {chatExpanded ? <ChevronUp className="ml-auto size-4" aria-hidden="true" /> : <ChevronDown className="ml-auto size-4" aria-hidden="true" />}
            </button>

            <div role="tablist" aria-label="Plan or chat" className="order-2 grid grid-cols-2 border-b border-line bg-surface lg:hidden">
              {(['plan', 'chat'] as const).map((t) => {
                const on = tab === t
                return (
                  <button
                    key={t}
                    id={`room-tab-${t}`}
                    type="button"
                    role="tab"
                    aria-selected={on}
                    aria-controls={t === 'plan' ? 'room-plan-panel' : 'room-chat-panel'}
                    onClick={() => setTab(t)}
                    className={cn(
                      'relative flex min-h-12 items-center justify-center gap-2 border-b-2 text-base font-semibold transition-colors',
                      on ? 'border-brand text-brand-text' : 'border-transparent text-ink-2 hover:bg-hover',
                    )}
                  >
                    {t === 'plan' ? 'Plan' : 'Chat'}
                    {t === 'chat' && unread > 0 && (
                      <span className="size-2.5 rounded-full bg-[var(--rw-danger)]" role="img" aria-label={`${unread} unread ${unread === 1 ? 'message' : 'messages'}`} />
                    )}
                    {t === 'plan' && planDot && !on && <span className="size-2.5 rounded-full bg-brand" role="img" aria-label="The plan changed" />}
                  </button>
                )
              })}
            </div>

            <section
              id="room-chat-panel"
              role={wide ? undefined : 'tabpanel'}
              aria-label="Chat"
              aria-labelledby={wide ? undefined : 'room-tab-chat'}
              className={cn('order-3 min-h-0 flex-1 flex-col', tab === 'chat' ? 'flex' : 'hidden', 'lg:order-none lg:flex')}
            >
              <Conversation
                room={room}
                me={me}
                messages={messages}
                onSend={sendMessage}
                onSummon={() => void summon()}
                onDismiss={() => void dismiss()}
                agentBusy={agentBusy}
                agentError={agentError}
                historyOpen={!wide || chatExpanded}
              />
            </section>
          </div>
        </main>
      </BoardFlashProvider>
    </div>
  )
}
