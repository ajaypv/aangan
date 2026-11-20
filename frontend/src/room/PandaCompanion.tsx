import { useEffect, useRef, useState, type PointerEvent, type ReactNode } from 'react'
import type { Room } from '@/types'
import { useFlash } from './useBoardFlash'
import type { useRoomRtc } from './useRoomRtc'
import './panda.css'

type PandaMood = 'idle' | 'ready' | 'connecting' | 'listening' | 'thinking' | 'planning' | 'speaking' | 'happy' | 'approval' | 'hello' | 'offline'
type Rtc = ReturnType<typeof useRoomRtc>

const MOODS: Record<PandaMood, { title: string; detail: string }> = {
  idle: { title: 'Where to, travel buddy?', detail: 'You bring the big ideas. I bring the tiny map.' },
  ready: { title: 'All ears. Round ones.', detail: 'Voice is on. I am ready when you are.' },
  connecting: { title: 'One panda, joining...', detail: 'Getting voice connected. Text still works.' },
  listening: { title: 'You have my full ears.', detail: 'Listening to the room. Keep those ideas coming.' },
  thinking: { title: 'Hmm... bamboo or beach?', detail: 'Mulling over the latest message.' },
  planning: { title: 'Tiny paws. Big plans.', detail: 'The trip board just changed. Take a peek!' },
  speaking: { title: 'Ooh, here is an idea!', detail: 'Aangan is speaking to the room.' },
  happy: { title: 'One step closer to adventure!', detail: 'I left a reply in the chat for you.' },
  approval: { title: 'Your call, captain.', detail: 'A decision is waiting on the plan board. You are in charge.' },
  hello: { title: 'Hi, travel buddy!', detail: 'A little wave before our next big adventure.' },
  offline: { title: 'A little connection hiccup.', detail: 'Voice is unavailable. We can still plan in chat.' },
}

function PandaHead() {
  return (
    <span className="panda-head">
      <span className="panda-ear panda-ear--left" />
      <span className="panda-ear panda-ear--right" />
      <span className="panda-face">
        <span className="panda-patch panda-patch--left" />
        <span className="panda-patch panda-patch--right" />
        <span className="panda-eye panda-eye--left"><i className="panda-pupil" /></span>
        <span className="panda-eye panda-eye--right"><i className="panda-pupil" /></span>
        <span className="panda-cheek panda-cheek--left" />
        <span className="panda-cheek panda-cheek--right" />
        <span className="panda-nose" />
        <span className="panda-mouth" />
      </span>
    </span>
  )
}

export function PandaAvatar() {
  return <span className="panda-avatar" aria-hidden="true"><PandaHead /></span>
}

function followPointer(event: PointerEvent<HTMLButtonElement>) {
  if (event.pointerType !== 'mouse') return
  const bounds = event.currentTarget.getBoundingClientRect()
  const x = Math.max(-1, Math.min(1, (event.clientX - bounds.left) / bounds.width * 2 - 1))
  const y = Math.max(-1, Math.min(1, (event.clientY - bounds.top) / bounds.height * 2 - 1))
  event.currentTarget.style.setProperty('--panda-look-x', `${x * 3}px`)
  event.currentTarget.style.setProperty('--panda-look-y', `${y * 2}px`)
}

export function PandaCompanion({ room, rtc, agentUid, connecting, controls }: { room: Room; rtc: Rtc; agentUid: string; connecting: boolean; controls?: ReactNode }) {
  const { sections } = useFlash()
  const lastMessage = room.messages.at(-1)
  const seenMessage = useRef(lastMessage?.id ?? 0)
  const [reaction, setReaction] = useState<'thinking' | 'happy' | null>(null)
  const reactionTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const [greeting, setGreeting] = useState(false)
  const greetingTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  useEffect(() => {
    if (!lastMessage || lastMessage.id <= seenMessage.current) return
    seenMessage.current = lastMessage.id
    clearTimeout(reactionTimer.current)
    const next = lastMessage.kind === 'user' ? 'thinking' : lastMessage.kind === 'agent' ? 'happy' : null
    setReaction(next)
    // The room has no planner-busy field: this is a bounded reaction, not a progress indicator.
    if (next) reactionTimer.current = setTimeout(() => setReaction(null), next === 'thinking' ? 10000 : 4000)
  }, [lastMessage])

  useEffect(() => () => {
    clearTimeout(reactionTimer.current)
    clearTimeout(greetingTimer.current)
  }, [])

  const agent = rtc.remote.find((remote) => remote.uid === agentUid)
  const voiceConnected = room.agent.live && rtc.status === 'connected' && !!agent
  const humanSpeaking = rtc.speaking.some((uid) => uid !== agentUid && (
    uid === rtc.localUid ? rtc.micOn : rtc.remote.some((remote) => remote.uid === uid && remote.hasAudio)
  ))
  let mood: PandaMood = voiceConnected ? 'ready' : 'idle'
  if (greeting) mood = 'hello'
  if (reaction) mood = reaction
  if (room.pending_approval?.status === 'waiting') mood = 'approval'
  if (sections.size > 0) mood = 'planning'
  if (voiceConnected && humanSpeaking) mood = 'listening'
  if (voiceConnected && rtc.speaking.includes(agentUid)) mood = 'speaking'
  if (connecting || (room.agent.live && !voiceConnected)) mood = 'connecting'
  if (room.agent.live && rtc.status === 'error') mood = 'offline'
  const copy = MOODS[mood]
  const voiceLabel = room.agent.live ? rtc.status === 'error' ? 'Voice unavailable' : voiceConnected ? 'Voice on' : 'Voice connecting' : 'Text companion'

  const greet = () => {
    clearTimeout(greetingTimer.current)
    setGreeting(true)
    greetingTimer.current = setTimeout(() => setGreeting(false), 2600)
  }

  return (
    <aside className="room-companion" data-mood={mood} data-greeting={greeting} aria-label="Aangan, your panda trip companion">
      <button
        type="button"
        className="panda-play"
        onPointerMove={followPointer}
        onPointerLeave={(event) => {
          event.currentTarget.style.removeProperty('--panda-look-x')
          event.currentTarget.style.removeProperty('--panda-look-y')
        }}
        onClick={greet}
        aria-label="Say hello to Aangan the panda"
        title="Give your trip buddy a wave"
      >
        <span className="panda-halo" aria-hidden="true" />
        <span className="panda-thought" aria-hidden="true"><i /><i /><i /></span>
        <span className="panda-spark panda-spark--one" aria-hidden="true">+</span>
        <span className="panda-spark panda-spark--two" aria-hidden="true">+</span>
        <span className="panda-rig" aria-hidden="true">
          <span className="panda-shadow" />
          <span className="panda-body" />
          <span className="panda-foot panda-foot--left" />
          <span className="panda-foot panda-foot--right" />
          <span className="panda-scarf" />
          <PandaHead />
          <span className="panda-map">
            <svg viewBox="0 0 90 40" fill="none">
              <path d="M30 2v36M60 2v36" stroke="#c0cbb5" />
              <path d="M10 30c9-22 22 9 35-5S60 8 73 13" stroke="#638878" strokeWidth="2" strokeDasharray="3 3" />
              <path d="M78 12c0 4-5 8-5 8s-5-4-5-8a5 5 0 0 1 10 0Z" fill="#c16b4d" />
              <circle cx="73" cy="12" r="1.5" fill="#fff8e8" />
            </svg>
          </span>
          <span className="panda-paw panda-paw--left" />
          <span className="panda-paw panda-paw--right"><span className="panda-pencil" /></span>
        </span>
      </button>
      <div className="room-companion-copy" role="status" aria-live="polite" aria-atomic="true">
        <div className="room-companion-name">
          <strong>Aangan</strong>
          <h2>{copy.title}</h2>
          <span className="room-companion-mode" title={voiceLabel}>
            <i data-live={voiceConnected} aria-hidden="true" />
            <span className="room-companion-mode-text">{voiceLabel}</span>
          </span>
        </div>
        <p title={copy.detail}>{copy.detail}</p>
      </div>
      {controls}
    </aside>
  )
}
