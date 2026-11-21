import { useEffect, useMemo, useRef, useState } from 'react'
import { Conversation, ConversationContent, ConversationScrollButton } from '@/components/ai-elements/conversation'
import { Message, MessageContent, MessageResponse } from '@/components/ai-elements/message'
import { Shimmer } from '@/components/ai-elements/shimmer'
import { Composer } from '@/components/ask/Composer'
import { DidSummary } from '@/components/ask/DidSummary'
import { EmptyAsk } from '@/components/ask/EmptyAsk'
import { ProposalCard } from '@/components/ask/ProposalCard'
import { useVoiceExtras } from '@/components/ask/useVoiceExtras'
import { VoicePanel, VoiceSetupNotice } from '@/components/voice/VoicePanel'
import { agentMeta, memberOf } from '@/lib/format'
import { useApp } from '@/state/AppState'
import type { Snapshot, ToolEvent } from '@/types'
import { Button } from '@/ui/primitives'
import { HouseStatus } from '@/house/HouseStatus'

/** Each tool call belongs to the first agent reply spoken at or after it. */
function eventsByReply(snap: Snapshot): Map<number, ToolEvent[]> {
  const replies = snap.transcript.map((e, i) => (e.role === 'agent' ? i : -1)).filter((i) => i >= 0)
  const map = new Map<number, ToolEvent[]>()
  for (const ev of snap.events) {
    const target = replies.find((i) => snap.transcript[i].ts >= ev.ts)
    if (target !== undefined) map.set(target, [...(map.get(target) ?? []), ev])
  }
  return map
}

const hhmm = (ts: string) => ts.slice(0, 5)

/** Who answered, in a few quiet words: the specialist's colour, its name and the time. */
function Answerer({ agent, ts }: { agent: string | null; ts: string }) {
  const meta = agentMeta(agent)
  return (
    <p className="flex items-center gap-1.5 pl-1 text-xs text-ink-2">
      <span className="size-2 rounded-full" style={{ background: meta.color }} aria-hidden="true" />
      <span className="font-semibold text-ink">{meta.label}</span>
      {ts && <time className="num">{hhmm(ts)}</time>}
    </p>
  )
}

export function Ask() {
  const { snap, personaId, outbox, busy, online, say, voice, voiceActive, startVoice, stopVoice, config } = useApp()
  const [draft, setDraft] = useState('')
  const [unsent, setUnsent] = useState<string | null>(null)
  const [setupOpen, setSetupOpen] = useState(false)
  const micRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLHeadingElement>(null)
  const length = useRef(0)
  length.current = snap?.transcript.length ?? 0

  const grouped = useMemo(() => (snap ? eventsByReply(snap) : new Map<number, ToolEvent[]>()), [snap])
  const extras = useVoiceExtras(snap?.transcript.length ?? 0, personaId)

  // Focus follows the call: into the voice panel when it opens, back to the mic button when it closes.
  const lastPhase = useRef(voice.phase)
  useEffect(() => {
    const before = lastPhase.current
    lastPhase.current = voice.phase
    // Every panel (connecting, live, error, ending) has its own heading, so focus is re-placed whenever the panel changes.
    if (voice.phase !== 'idle' && before !== voice.phase) panelRef.current?.focus()
    else if (before !== 'idle' && voice.phase === 'idle') micRef.current?.focus()
  }, [voice.phase])

  if (!snap || !personaId) return null
  const me = memberOf(snap, personaId)
  if (!me) return null

  const voiceReady = config?.services.voice.configured ?? false
  const native = config?.language_mode === 'native' && (me.language === 'Hindi' || me.language === 'Hinglish')

  const send = async (text: string) => {
    const value = text.trim()
    if (!value || busy || !online) return
    setUnsent(null)
    setDraft('')
    const before = length.current
    await say(value)
    await new Promise((r) => window.setTimeout(r, 60)) // let the new snapshot render before checking it
    if (length.current === before) {
      // Nothing was recorded, so it did not go through: put the words back so nothing is lost.
      setDraft((d) => d || value)
      setUnsent(value)
    }
  }

  const onVoice = () => {
    if (voiceActive) {
      void stopVoice()
      return
    }
    if (!voiceReady) {
      setSetupOpen(true)
      return
    }
    setSetupOpen(false)
    void startVoice()
  }

  const mine = snap.transcript.filter((e) => e.member_id === personaId)
  const empty = mine.length === 0 && !outbox && !extras.greeting && !voiceActive
  const lastMine = mine[mine.length - 1]
  const greetingNode = extras.greeting && (
    <div key="voice-greeting" className="rise space-y-1.5">
      <Answerer agent="aangan" ts="" />
      <Message from="assistant">
        <MessageContent>
          <MessageResponse>{extras.greeting.text}</MessageResponse>
        </MessageContent>
      </Message>
    </div>
  )

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col">
      <VoicePanel headingRef={panelRef} />
      <HouseStatus />
      <Conversation className="min-h-0 flex-1">
        <ConversationContent className="gap-5 px-4 py-4" aria-label="Conversation with Aangan">
          {empty && <EmptyAsk snap={snap} me={me} busy={busy || !online} onSend={(t) => void send(t)} onVoice={onVoice} />}
          {snap.transcript.map((entry, i) => {
            const before = extras.greeting && extras.greeting.at === i ? greetingNode : null
            if (entry.member_id !== personaId) return before
            if (entry.role === 'user') {
              return (
                <div key={i} className="contents">
                  {before}
                  <Message from="user">
                    <MessageContent>{entry.text}</MessageContent>
                  </Message>
                </div>
              )
            }
            const events = grouped.get(i)
            return (
              <div key={i} className="contents">
                {before}
                <div className="rise space-y-1.5">
                  <Answerer agent={entry.agent} ts={entry.ts} />
                  <Message from="assistant">
                    <MessageContent>
                      <MessageResponse>{entry.text}</MessageResponse>
                    </MessageContent>
                  </Message>
                  {events && <DidSummary events={events} snap={snap} />}
                </div>
              </div>
            )
          })}
          {extras.greeting && extras.greeting.at >= snap.transcript.length && greetingNode}
          {outbox && outbox.member_id === personaId && (
            <Message from="user">
              <MessageContent>{outbox.text}</MessageContent>
            </Message>
          )}
          {extras.liveUser && (
            <Message from="user" className={extras.listeningNow ? 'opacity-70' : undefined}>
              <MessageContent>
                {extras.liveUser}
                {extras.listeningNow && (
                  <span className="ml-1 text-ink-2" aria-label="still listening">
                    …
                  </span>
                )}
              </MessageContent>
            </Message>
          )}
          {busy && (
            <div role="status" className="pl-1">
              <Shimmer className="text-sm">Aangan is thinking…</Shimmer>
            </div>
          )}
          {snap.pending && lastMine?.role === 'agent' && !busy && <ProposalCard native={native} />}
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>

      {setupOpen && !voiceReady && <VoiceSetupNotice onClose={() => setSetupOpen(false)} />}
      {unsent && (
        <div className="flex items-center justify-between gap-3 border-t border-line bg-danger-bg px-4 py-2.5 text-sm" role="alert">
          <span className="text-[var(--rw-text-danger)]">That message did not send, and it is still in the box.</span>
          <Button size="sm" variant="secondary" disabled={busy || !online} onClick={() => void send(unsent)}>
            Try again
          </Button>
        </div>
      )}
      <Composer
        value={draft}
        onChange={setDraft}
        onSubmit={() => void send(draft)}
        busy={busy}
        offline={!online}
        voicePhase={voice.phase}
        onVoice={onVoice}
        micRef={micRef}
        placeholder={native ? 'Bolo ya likho…' : 'Ask Aangan anything…'}
      />
    </div>
  )
}
