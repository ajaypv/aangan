import { Check, Hand, Info, Loader2, Mic, MicOff, PhoneOff, Plug, RefreshCw, Sparkles, TriangleAlert, Volume2, X } from 'lucide-react'
import { useEffect, useState, type Ref } from 'react'
import { Orb, type OrbState } from '@/components/ask/Orb'
import { memberOf } from '@/lib/format'
import { STEP_LABELS, STEP_ORDER, type StepId, type StepStatus, type VoiceState } from '@/lib/voiceSession'
import { cn } from '@/lib/utils'
import { useApp } from '@/state/AppState'
import { Avatar, Button, IconButton } from '@/ui/primitives'

function orbState(v: VoiceState): OrbState {
  if (v.phase === 'connecting' || v.phase === 'waiting-agent') return 'connecting'
  if (v.muted) return 'muted'
  if (v.agentState === 'thinking') return 'thinking'
  if (v.agentState === 'speaking') return 'speaking'
  return 'listening'
}

function stateLabel(v: VoiceState): string {
  if (v.rtcState === 'RECONNECTING') return 'Reconnecting…'
  if (v.muted) return 'Muted'
  if (v.agentState === 'thinking') return 'Thinking…'
  if (v.agentState === 'speaking') return 'Aangan is speaking'
  return 'Listening'
}

function stepIcon(status: StepStatus) {
  if (status === 'active') return <Loader2 className="size-4 animate-spin text-brand-text" aria-label="In progress" />
  if (status === 'done') return <Check className="size-4 text-[var(--rw-text-success)]" aria-label="Done" />
  if (status === 'failed') return <X className="size-4 text-[var(--rw-text-danger)]" aria-label="Failed" />
  if (status === 'skipped') return <span className="inline-block size-4 text-center text-xs text-ink-2" aria-label="Skipped">–</span>
  return <span className="inline-block size-2 rounded-full bg-[rgb(var(--rw-neutral-60))]" aria-label="Waiting" />
}

function useElapsed(running: boolean) {
  const [s, setS] = useState(0)
  useEffect(() => {
    if (!running) return setS(0)
    const t0 = Date.now()
    const id = window.setInterval(() => setS(Math.floor((Date.now() - t0) / 1000)), 500)
    return () => window.clearInterval(id)
  }, [running])
  return s
}

const HEADING = 'sr-only'

/** The calm connecting state: one line saying what is happening now, and a way out. */
function Connecting({ v, headingRef }: { v: VoiceState; headingRef?: Ref<HTMLHeadingElement> }) {
  const { stopVoice, snap } = useApp()
  const member = snap && v.memberId ? memberOf(snap, v.memberId) : undefined
  const elapsed = useElapsed(v.phase === 'waiting-agent')
  const current = STEP_ORDER.find((id) => v.steps[id] === 'active') ?? (v.phase === 'waiting-agent' ? 'agent' : 'backend')
  return (
    <div className="flex items-center gap-3 px-3 py-2.5" aria-live="polite">
      <Orb state="connecting" size={56}>
        <Loader2 className="size-5 animate-spin" />
      </Orb>
      <div className="min-w-0 flex-1">
        <h2 ref={headingRef} tabIndex={-1} className="text-sm font-semibold outline-none">
          Connecting{member ? ` as ${member.name}` : ''}…
        </h2>
        <p className="t-secondary truncate">
          {STEP_LABELS[current as StepId]}
          {current === 'agent' && v.phase === 'waiting-agent' ? ` (${elapsed}s of 20s)` : ''}
        </p>
      </div>
      <Button variant="secondary" size="sm" onClick={() => void stopVoice()}>
        Cancel
      </Button>
    </div>
  )
}

/**
 * Voice mode as one slim call bar above the conversation, so the chat keeps the screen: the orb that swells with the voice, what Aangan is
 * doing, the words being said right now, and round controls (mute, interrupt while it speaks, end). Details live behind the info button.
 */
function Live({ v, headingRef, detailsOpen, onDetails }: { v: VoiceState; headingRef?: Ref<HTMLHeadingElement>; detailsOpen: boolean; onDetails: () => void }) {
  const { stopVoice, toggleMute, interruptVoice, snap } = useApp()
  const member = snap && v.memberId ? memberOf(snap, v.memberId) : undefined
  const state = orbState(v)
  const speaking = v.agentState === 'speaking'
  const last = v.turns[v.turns.length - 1]
  const caption = last ? (last.who === 'user' ? `“${last.text}”` : last.text) : 'Go ahead, I am listening.'
  const warning = v.issues.find((i) => (i.source === 'agent' || i.source === 'rtm') && Date.now() - i.at < 45_000)
  return (
    <div className="px-3 py-2.5">
      <h2 ref={headingRef} tabIndex={-1} className="sr-only outline-none">
        Voice conversation with Aangan
      </h2>
      <div className="flex items-center gap-3">
        <Orb state={state} source={v.muted ? 'none' : speaking ? 'agent' : 'mic'} size={56}>
          {state === 'muted' ? <MicOff className="size-5" /> : state === 'thinking' ? <Sparkles className="size-5" /> : state === 'speaking' ? <Volume2 className="size-5" /> : <Mic className="size-5" />}
        </Orb>
        <div className="min-w-0 flex-1">
          <p className="flex items-center gap-1.5 text-sm font-semibold" role="status" aria-live="polite">
            {member && <Avatar member={member} size={18} />}
            {stateLabel(v)}
          </p>
          <p className={cn('line-clamp-2 text-sm', last?.who === 'user' ? 'text-ink-2' : 'text-ink')} aria-live="off">
            {caption}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <IconButton
            label={v.muted ? 'Unmute' : 'Mute'}
            variant="secondary"
            tooltip={false}
            aria-pressed={v.muted}
            className="size-10 rounded-full lg:size-10"
            onClick={() => void toggleMute()}
          >
            {v.muted ? <MicOff className="size-[18px]" /> : <Mic className="size-[18px]" />}
          </IconButton>
          {speaking && (
            <IconButton label="Interrupt" variant="secondary" tooltip={false} disabled={!v.rtmReady} className="size-10 rounded-full lg:size-10" onClick={() => void interruptVoice()}>
              <Hand className="size-[18px]" />
            </IconButton>
          )}
          <IconButton
            label="Details"
            variant="tertiary"
            tooltip={false}
            aria-expanded={detailsOpen}
            className="relative size-10 rounded-full lg:size-10"
            onClick={onDetails}
          >
            <Info className="size-[18px]" />
            {v.issues.length > 0 && <span className="absolute right-1.5 top-1.5 size-2.5 rounded-full bg-[var(--rw-warning)] ring-2 ring-surface" role="img" aria-label={`${v.issues.length} notices`} />}
          </IconButton>
          <IconButton label="End call" variant="secondary" tooltip={false} className="size-10 rounded-full !bg-[var(--rw-danger)] !text-white hover:!bg-[rgb(var(--rw-danger-130))] lg:size-10" onClick={() => void stopVoice()}>
            <PhoneOff className="size-[18px]" />
          </IconButton>
        </div>
      </div>
      {!v.rtmReady && <p className="t-caption mt-1.5 pl-[68px]">Live captions are not connected, so the status and interrupt are limited. You can still talk.</p>}
      {warning && (
        <p className="mt-1.5 flex items-start gap-1.5 pl-[68px] text-xs text-[var(--rw-text-danger)]" role="alert">
          <TriangleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
          <span>{warning.message}</span>
        </p>
      )}
    </div>
  )
}

function Problem({ v, headingRef }: { v: VoiceState; headingRef?: Ref<HTMLHeadingElement> }) {
  const { startVoice, dismissVoiceError, setTab, reload } = useApp()
  const e = v.error
  if (!e) return null
  const setup = e.kind === 'not-configured' || e.kind === 'no-household'
  return (
    <div className={cn('px-4 py-4', setup ? 'bg-surface-3' : 'bg-danger-bg')} role="alert">
      <div className="mx-auto flex max-w-xl items-start gap-3">
        {setup ? <Plug className="mt-0.5 size-5 shrink-0 text-ink-2" aria-hidden="true" /> : <TriangleAlert className="mt-0.5 size-5 shrink-0 text-[var(--rw-text-danger)]" aria-hidden="true" />}
        <div className="min-w-0 flex-1 text-sm">
          <h2 ref={headingRef} tabIndex={-1} className="font-semibold outline-none">
            {e.title}
          </h2>
          <p className="t-secondary">{e.detail}</p>
          {e.hints.length > 0 && (
            <ul className="t-secondary mt-1.5 list-disc space-y-0.5 pl-4">
              {e.hints.map((h) => (
                <li key={h}>{h}</li>
              ))}
            </ul>
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            {e.kind === 'no-household' ? (
              <Button size="sm" onClick={() => { dismissVoiceError(); reload() }}>
                Set up Aangan
              </Button>
            ) : setup ? (
              <Button size="sm" variant="secondary" onClick={() => setTab('settings')}>
                Open Settings
              </Button>
            ) : (
              <Button size="sm" icon={<RefreshCw className="size-4" aria-hidden="true" />} onClick={() => void startVoice()}>
                Try again
              </Button>
            )}
            <Button size="sm" variant="tertiary" onClick={dismissVoiceError}>
              Dismiss
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

/** Shown when someone taps the mic before voice is connected: plain, short, and a way forward. Text chat keeps working. */
export function VoiceSetupNotice({ onClose }: { onClose: () => void }) {
  const { config, setTab } = useApp()
  const missing = config?.services.voice.missing ?? []
  return (
    <div className="border-t border-line bg-surface-3 px-4 py-3" role="status">
      <div className="mx-auto flex max-w-3xl items-start gap-3 text-sm">
        <Plug className="mt-0.5 size-5 shrink-0 text-ink-2" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="font-semibold">Voice is not connected yet</p>
          <p className="t-secondary">
            {missing.length > 0 ? (
              <>
                Still needed: <span className="font-mono text-xs">{missing.join(', ')}</span>.{' '}
              </>
            ) : null}
            You can keep typing to Aangan in the meantime.
          </p>
          <div className="mt-2 flex gap-2">
            <Button size="sm" variant="secondary" onClick={() => setTab('settings')}>
              Open Settings
            </Button>
            <Button size="sm" variant="tertiary" onClick={onClose}>
              Dismiss
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

const row = 'flex justify-between gap-3 py-1'

/** The call's technical details. Closed unless the person opens them; scrolls inside itself so it can never push the chat off the screen. */
function ConnectionDetails({ v }: { v: VoiceState }) {
  const s = v.session
  const yesNo = (b: boolean) => (b ? 'yes' : 'no')
  return (
    <div className="max-h-[40dvh] overflow-y-auto border-t border-line bg-bg px-4 py-3 text-xs">
      <div className="mx-auto max-w-3xl">
        <dl className="divide-y divide-line">
          <div className={row}><dt className="text-ink-2">Channel</dt><dd className="num break-all font-mono">{s?.channel ?? '-'}</dd></div>
          <div className={row}><dt className="text-ink-2">Agent id</dt><dd className="break-all font-mono">{s?.agent_id ?? '-'}</dd></div>
          <div className={row}><dt className="text-ink-2">Your uid / agent uid</dt><dd className="num font-mono">{s ? `${s.uid} / ${s.agent_uid ?? '-'}` : '-'}</dd></div>
          <div className={row}><dt className="text-ink-2">Voice</dt><dd>{s?.voice ? `${s.voice.name} (${s.voice.locale})` : '-'}</dd></div>
          <div className={row}><dt className="text-ink-2">Language mode</dt><dd>{s?.language_mode ?? '-'}</dd></div>
          <div className={row}><dt className="text-ink-2">Audio connection</dt><dd>{v.rtcState.toLowerCase()}</dd></div>
          <div className={row}><dt className="text-ink-2">Live captions (RTM) connected</dt><dd>{yesNo(v.rtmReady)}</dd></div>
          <div className={row}><dt className="text-ink-2">Aangan is in the channel</dt><dd>{yesNo(v.agentJoined)}</dd></div>
          <div className={row}><dt className="text-ink-2">Agent state</dt><dd>{v.agentState ?? '-'}</dd></div>
        </dl>
        <ol className="mt-2 space-y-1">
          {STEP_ORDER.map((id) => (
            <li key={id} className="flex items-center gap-2">
              {stepIcon(v.steps[id])}
              <span className={cn(v.steps[id] === 'pending' && 'text-ink-2')}>{STEP_LABELS[id]}</span>
            </li>
          ))}
        </ol>
        {v.metrics.length > 0 && <p className="mt-2 text-ink-2">Latest timings: {v.metrics.map((m) => `${m.name} ${Math.round(m.value)} ms`).join(', ')}</p>}
        <div className="mt-2" aria-label="Recent notices">
          <p className="font-semibold">Last error and notices</p>
          {v.error && (
            <p className="text-[var(--rw-text-danger)]">
              {v.error.title}: {v.error.detail}
            </p>
          )}
          {v.issues.length === 0 && !v.error && <p className="text-ink-2">None.</p>}
          <ul className="space-y-0.5">
            {v.issues.map((i) => (
              <li key={i.id}>
                <span className="num text-ink-2">{new Date(i.at).toLocaleTimeString()}</span> <span className="font-semibold">{i.source}</span>
                {i.code !== undefined && i.code !== '' ? ` (${i.code})` : ''}: {i.message}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}

/** Everything about a voice call that sits above the conversation. It renders nothing while there is no call and no problem. */
export function VoicePanel({ headingRef }: { headingRef?: Ref<HTMLHeadingElement> }) {
  const { voice: v } = useApp()
  const [details, setDetails] = useState(false)
  useEffect(() => {
    if (v.phase === 'idle') setDetails(false)
  }, [v.phase])
  if (v.phase === 'idle') return null
  const toggle = () => setDetails((d) => !d)
  const hasNotes = v.issues.length > 0 || v.error !== null
  return (
    <section aria-label="Voice conversation" className="border-b border-line bg-surface">
      {(v.phase === 'connecting' || v.phase === 'waiting-agent') && <Connecting v={v} headingRef={headingRef} />}
      {v.phase === 'live' && <Live v={v} headingRef={headingRef} detailsOpen={details} onDetails={toggle} />}
      {v.phase === 'ending' && (
        <div className="px-4 py-3 text-center text-sm font-semibold" role="status">
          <h2 ref={headingRef} tabIndex={-1} className={HEADING}>
            Ending the call
          </h2>
          <span aria-hidden="true">Ending the call…</span>
        </div>
      )}
      {v.phase === 'error' && <Problem v={v} headingRef={headingRef} />}
      {v.phase !== 'live' && v.phase !== 'ending' && hasNotes && (
        <button type="button" onClick={toggle} aria-expanded={details} className="flex min-h-9 w-full items-center justify-center gap-1.5 border-t border-line text-xs font-semibold text-ink-2">
          <Info className="size-3.5" aria-hidden="true" />
          {details ? 'Hide details' : `Details (${v.issues.length} ${v.issues.length === 1 ? 'notice' : 'notices'})`}
        </button>
      )}
      {details && <ConnectionDetails v={v} />}
    </section>
  )
}
