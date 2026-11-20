import { Mic, PhoneOff, SendHorizontal, Sparkles } from 'lucide-react'
import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { cn } from '@/lib/utils'
import type { Participant, Room, RoomMessage } from '@/types'
import { Avatar, Button } from '@/ui/primitives'
import { avatarOf } from './format'
import { PandaAvatar } from './PandaCompanion'
import type { PendingMessage } from './useRoom'

/* Text is shown exactly as given. `lang` lets the browser pick the right script (Telugu, Kannada, Hindi) for each message. */
const BODY = 'whitespace-pre-wrap break-words text-[0.9375rem] leading-snug'

function UserBubble({ m, mine, room }: { m: RoomMessage | PendingMessage; mine: boolean; room: Room }) {
  const who = room.participants.find((p) => p.id === m.participant_id)
  const pending = 'pending' in m
  return (
    <li className={cn('flex gap-2', mine ? 'justify-end' : 'justify-start')} data-kind="user">
      {!mine && who && <Avatar member={avatarOf(who)} size={28} className="mt-5" />}
      <div className={cn('flex min-w-0 max-w-[85%] flex-col', mine ? 'items-end' : 'items-start')}>
        <p className="t-caption mb-0.5 px-1">
          {mine ? 'You' : m.name || who?.name} <span className="num">{m.ts}</span>
        </p>
        <p
          lang={m.lang}
          className={cn(BODY, 'rounded-2xl px-3.5 py-2', mine ? 'rounded-br-md bg-brand text-brand-ink' : 'rounded-bl-md border border-line bg-surface', pending && 'opacity-70')}
        >
          {m.text}
        </p>
        {pending && <span className="sr-only">Sending</span>}
      </div>
    </li>
  )
}

function AgentCard({ m }: { m: RoomMessage }) {
  return (
    <li className="flex gap-2" data-kind="agent">
      <span className="mt-5 shrink-0">
        <PandaAvatar />
      </span>
      <div className="min-w-0 max-w-[92%]">
        <p className="t-caption mb-0.5 px-1">
          <span className="font-semibold text-brand-text">Aangan</span> <span className="num">{m.ts}</span>
        </p>
        <div className="rounded-2xl rounded-bl-md border border-[var(--selected-edge)] bg-brand-soft px-3.5 py-2.5 shadow-xs">
          <p lang={m.lang} className={BODY}>
            {m.text}
          </p>
        </div>
      </div>
    </li>
  )
}

function SystemLine({ m }: { m: RoomMessage }) {
  return (
    <li className="flex justify-center" data-kind="system">
      <p className="t-caption max-w-[90%] rounded-full bg-surface-2 px-3 py-1 text-center">
        {m.text} <span className="num">{m.ts}</span>
      </p>
    </li>
  )
}

/** The conversation: messages with your bubbles on the right and Aangan's cards in brand colour, then the message box and the voice button. */
export function Conversation({
  room,
  me,
  messages,
  onSend,
  onSummon,
  onDismiss,
  agentBusy,
  agentError,
  historyOpen = true,
}: {
  room: Room
  me: Participant | undefined
  messages: (RoomMessage | PendingMessage)[]
  onSend: (text: string, ask: boolean) => Promise<boolean>
  onSummon: () => void
  onDismiss: () => void
  agentBusy: boolean
  agentError: string | null
  historyOpen?: boolean
}) {
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const area = useRef<HTMLTextAreaElement>(null)
  const scroller = useRef<HTMLDivElement>(null)
  const stick = useRef(true)
  const live = room.agent.live

  // Follow the conversation while you are at the bottom, or when you have just sent something.
  const last = messages[messages.length - 1]
  useEffect(() => {
    const el = scroller.current
    if (!el || !historyOpen) return
    const mine = last && last.participant_id === me?.id && last.kind === 'user'
    if (stick.current || mine) {
      const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
      el.scrollTo({ top: el.scrollHeight, behavior: reduce ? 'auto' : 'smooth' })
    }
  }, [messages.length, last, me?.id, historyOpen])

  useEffect(() => {
    const el = area.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`
  }, [text])

  const send = async (ask: boolean) => {
    const value = text.trim()
    if (!value) {
      area.current?.focus()
      return
    }
    setText('')
    setError(null)
    stick.current = true
    const ok = await onSend(value, ask)
    if (!ok) {
      setText((cur) => cur || value)
      setError('That message did not send. It is back in the box: try again.')
    }
  }

  const keydown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      void send(false)
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div
        id="room-conversation-history"
        ref={scroller}
        onScroll={(e) => {
          const el = e.currentTarget
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120
        }}
        className={cn('min-h-0 flex-1 overflow-y-auto px-3 py-3', !historyOpen && 'hidden')}
        tabIndex={0}
        role="log"
        aria-label="Conversation"
        aria-live="polite"
      >
        {messages.length === 0 ? (
          <p className="t-secondary mx-auto mt-6 max-w-xs text-center">Say hello. Talk about the trip and Aangan keeps the plan; write “Aangan” to ask it something.</p>
        ) : (
          <ul className="space-y-3">
            {messages.map((m) =>
              m.kind === 'agent' ? <AgentCard key={m.id} m={m} /> : m.kind === 'system' ? <SystemLine key={m.id} m={m} /> : <UserBubble key={m.id} m={m} mine={m.participant_id === me?.id} room={room} />,
            )}
          </ul>
        )}
      </div>

      {!historyOpen && (
        <div className="room-chat-rest">
          <p className="font-semibold text-ink">More trip. Less transcript.</p>
          <p>Talk together, watch the plan take shape, or send a quick idea below.</p>
        </div>
      )}

      <form
        className="mt-auto shrink-0 border-t border-line bg-bg px-3 pb-[max(0.625rem,env(safe-area-inset-bottom))] pt-2.5"
        onSubmit={(e) => {
          e.preventDefault()
          void send(false)
        }}
      >
        <div className="flex items-end rounded-[1.75rem] border border-edge bg-surface pl-4 pr-1.5 shadow-xs transition-colors focus-within:border-[var(--rw-text-primary)]">
          <label htmlFor="room-input" className="sr-only">
            Message the room
          </label>
          <textarea
            id="room-input"
            ref={area}
            rows={1}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={keydown}
            placeholder="Message the family"
            enterKeyHint="send"
            autoComplete="off"
            className="max-h-[120px] min-h-12 min-w-0 flex-1 resize-none bg-transparent py-3 text-base leading-snug text-ink outline-none placeholder:text-ink-2 focus-visible:outline-none"
          />
          <button
            type="submit"
            aria-label="Send message"
            disabled={!text.trim()}
            className="my-1 grid size-11 shrink-0 place-items-center rounded-full bg-brand text-brand-ink transition-opacity hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-30 lg:size-10"
          >
            <SendHorizontal className="size-[18px]" aria-hidden="true" />
          </button>
        </div>
        {error && (
          <p role="alert" className="mt-1.5 px-2 text-sm font-medium text-[var(--rw-text-danger)]">
            {error}
          </p>
        )}
        <div className="mt-2 flex flex-wrap gap-2">
          <Button variant="secondary" size="sm" icon={<Sparkles className="size-4" aria-hidden="true" />} onClick={() => void send(true)} className="flex-1">
            Ask Aangan
          </Button>
          {live ? (
            <Button variant="danger" size="sm" loading={agentBusy} icon={<PhoneOff className="size-4" aria-hidden="true" />} onClick={onDismiss} aria-label="Dismiss Aangan (stop the voice assistant)" className="flex-1">
              Dismiss
            </Button>
          ) : (
            <Button size="sm" loading={agentBusy} icon={<Mic className="size-4" aria-hidden="true" />} onClick={onSummon} className="flex-1">
              Talk to Aangan
            </Button>
          )}
        </div>
        {agentError && (
          <p role="alert" className="mt-1.5 px-2 text-sm font-medium text-[var(--rw-text-danger)]">
            {agentError}
          </p>
        )}
      </form>
    </div>
  )
}
