import { Loader2, Mic, PhoneOff, SendHorizontal } from 'lucide-react'
import { useEffect, useRef, type KeyboardEvent, type RefObject } from 'react'
import type { VoicePhase } from '@/lib/voiceSession'
import { cn } from '@/lib/utils'

/**
 * The one bar at the bottom of Ask, in the usual chat shape: a rounded field with the send button inside it, and the mic beside it. Enter
 * sends, Shift+Enter adds a line. The text is controlled by the screen so it can be put back if sending fails.
 */
export function Composer({
  value,
  onChange,
  onSubmit,
  busy,
  offline,
  voicePhase,
  onVoice,
  micRef,
  placeholder,
}: {
  value: string
  onChange: (v: string) => void
  onSubmit: () => void
  busy: boolean
  offline: boolean
  voicePhase: VoicePhase
  onVoice: () => void
  micRef: RefObject<HTMLButtonElement | null>
  placeholder: string
}) {
  const area = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const el = area.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 132)}px`
  }, [value])

  const keydown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      onSubmit()
    }
  }

  const connecting = voicePhase === 'connecting' || voicePhase === 'waiting-agent'
  const live = voicePhase === 'live'
  const ending = voicePhase === 'ending'
  const micLabel = live ? 'End voice conversation' : connecting ? 'Cancel voice connection' : ending ? 'Ending voice conversation' : 'Talk to Aangan'
  const canSend = value.trim().length > 0 && !busy && !offline

  return (
    <form
      className="border-t border-line bg-bg px-3 pb-2.5 pt-2.5"
      onSubmit={(e) => {
        e.preventDefault()
        if (canSend) onSubmit()
      }}
    >
      {offline && (
        <p className="mb-2 text-center text-sm text-[var(--rw-text-warning)]" role="status">
          You are offline. Reconnect to talk to Aangan.
        </p>
      )}
      <div className="mx-auto flex max-w-3xl items-end gap-2">
        {/* The field is one pill: focus firms its edge, and send sits inside it. */}
        <div className="flex min-w-0 flex-1 items-end rounded-[1.75rem] border border-edge bg-surface pl-4 pr-1.5 shadow-xs transition-colors focus-within:border-[var(--rw-text-primary)]">
          <label htmlFor="ask-input" className="sr-only">
            Message Aangan
          </label>
          <textarea
            id="ask-input"
            ref={area}
            rows={1}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={keydown}
            disabled={offline}
            placeholder={offline ? 'Offline' : placeholder}
            enterKeyHint="send"
            autoComplete="off"
            className="max-h-[132px] min-h-12 min-w-0 flex-1 resize-none bg-transparent py-3 text-base leading-snug text-ink outline-none placeholder:text-ink-2 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-60"
          />
          <button
            type="submit"
            aria-label="Send message"
            disabled={!canSend}
            className="my-1 grid size-10 shrink-0 place-items-center rounded-full bg-brand text-brand-ink transition-opacity hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-30"
          >
            <SendHorizontal className="size-[18px]" aria-hidden="true" />
          </button>
        </div>
        <button
          ref={micRef}
          type="button"
          aria-label={micLabel}
          disabled={ending || offline}
          onClick={onVoice}
          className={cn(
            'inline-flex size-12 shrink-0 select-none items-center justify-center rounded-full shadow-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50',
            live
              ? 'bg-[var(--rw-danger)] text-white hover:bg-[rgb(var(--rw-danger-130))]'
              : connecting
                ? 'border border-edge bg-surface text-ink hover:bg-hover'
                : 'bg-brand text-brand-ink hover:bg-brand-hover',
          )}
        >
          {live ? <PhoneOff className="size-5" aria-hidden="true" /> : connecting || ending ? <Loader2 className="size-5 animate-spin" aria-hidden="true" /> : <Mic className="size-5" aria-hidden="true" />}
        </button>
      </div>
    </form>
  )
}
