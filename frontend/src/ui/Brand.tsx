import { Mic, MicOff, Radio, Repeat, Settings } from 'lucide-react'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { memberOf } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useApp } from '@/state/AppState'
import { Avatar, IconButton, Pill, StatusDot, Tooltip, type Tone } from './primitives'

const MARK = `url('${import.meta.env.BASE_URL}brand-mark.svg')`

/** The courtyard mark (a sun over a doorway arch) drawn in brand teal. */
export function BrandMark({ size = 32, className }: { size?: number; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn('inline-block shrink-0 bg-brand', className)}
      style={{ width: size, height: size, mask: `${MARK} center / contain no-repeat`, WebkitMask: `${MARK} center / contain no-repeat` }}
    />
  )
}

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-2', className)}>
      <BrandMark />
      <span translate="no" className="text-xl font-extrabold leading-none tracking-tight text-ink">
        Aangan
      </span>
    </span>
  )
}

/** One small dot for the connection: green when voice is ready, teal while live, amber when voice is not connected, red when offline. */
export function ConnectionDot() {
  const { config, voice, online } = useApp()
  let tone: Tone = 'neutral'
  let text = 'Connecting'
  if (!online) {
    tone = 'danger'
    text = 'Offline'
  } else if (voice.phase === 'live') {
    tone = 'brand'
    text = 'Voice is live'
  } else if (config?.services.voice.configured) {
    tone = 'success'
    text = 'Connected, voice ready'
  } else if (config) {
    tone = 'warning'
    text = 'Connected, voice not set up'
  }
  return (
    <Tooltip label={text} side="bottom">
      <span role="img" aria-label={text} tabIndex={0} className="inline-grid size-6 place-items-center rounded-full">
        <StatusDot tone={tone} className="size-2.5" />
      </span>
    </Tooltip>
  )
}

/** Voice readiness, language mode and brain, as quiet chips (used by Settings). `compact` keeps just voice and language. */
export function ConnectionChips({ compact = false, className }: { compact?: boolean; className?: string }) {
  const { config, voice } = useApp()
  if (!config) return null
  const live = voice.phase === 'live'
  const ready = config.services.voice.configured
  return (
    <ul className={cn('flex flex-wrap items-center gap-1.5', className)} aria-label="Connection status">
      <li>
        <Pill tone={live ? 'brand' : ready ? 'success' : 'warning'}>
          <StatusDot tone={live ? 'brand' : ready ? 'success' : 'warning'} />
          {live ? 'Voice live' : ready ? 'Voice ready' : 'Voice not connected'}
        </Pill>
      </li>
      <li>
        <Pill>{config.language_mode === 'native' ? 'Native languages' : 'English'}</Pill>
      </li>
      {!compact && (
        <li>
          <Pill>{config.llm ? config.llm.model : 'Built-in brain'}</Pill>
        </li>
      )}
    </ul>
  )
}

/** Mute and a "Live" marker, shown only while a voice call is running. */
export function LiveControls() {
  const { voice, toggleMute } = useApp()
  if (voice.phase !== 'live') return null
  return (
    <div className="flex items-center gap-1.5">
      <IconButton label={voice.muted ? 'Unmute microphone' : 'Mute microphone'} variant="secondary" aria-pressed={voice.muted} onClick={() => void toggleMute()}>
        {voice.muted ? <MicOff className="size-4" /> : <Mic className="size-4" />}
      </IconButton>
      <span className="listening inline-flex items-center gap-1.5 rounded-md bg-brand px-2.5 py-1 text-xs font-bold text-brand-ink">
        <Radio className="size-3.5" aria-hidden="true" /> Live
      </span>
    </div>
  )
}

/** The signed-in person: their avatar opens a menu with Switch profile and Settings. */
export function UserMenu({ showName = false, align = 'end', side = 'bottom' }: { showName?: boolean; align?: 'start' | 'end'; side?: 'top' | 'bottom' }) {
  const { snap, personaId, clearMe, setTab } = useApp()
  const me = snap && personaId ? memberOf(snap, personaId) : undefined
  if (!me) return null
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={`${me.name}: account menu`}
          className="inline-flex min-h-11 items-center gap-2 rounded-full pr-1 transition-colors hover:bg-hover data-[state=open]:bg-hover lg:min-h-10"
        >
          <Avatar member={me} size={36} />
          {showName && (
            <span className="min-w-0 pr-2 text-left">
              <span className="block truncate text-sm font-semibold leading-tight">{me.name}</span>
              <span className="t-caption block truncate leading-tight">{me.relation}</span>
            </span>
          )}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align={align} side={side} className="w-56">
        <DropdownMenuLabel className="flex items-center gap-2.5 py-2">
          <Avatar member={me} size={32} />
          <span className="min-w-0">
            <span className="block truncate text-sm font-semibold">{me.name}</span>
            <span className="t-caption block truncate font-normal">{me.relation}</span>
          </span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem className="min-h-10" onSelect={() => clearMe()}>
          <Repeat /> Switch profile
        </DropdownMenuItem>
        <DropdownMenuItem className="min-h-10" onSelect={() => setTab('settings')}>
          <Settings /> Settings
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
