import { Check, ChevronLeft, Link2, LogOut, Share2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { Participant, Room } from '@/types'
import { Avatar, IconButton } from '@/ui/primitives'
import { avatarOf, plural } from './format'
import { inviteUrl } from './roomRoute'

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    // Older browsers and non-secure pages: a hidden field and the copy command.
    try {
      const area = document.createElement('textarea')
      area.value = text
      area.setAttribute('readonly', '')
      area.style.position = 'fixed'
      area.style.opacity = '0'
      document.body.appendChild(area)
      area.select()
      const ok = document.execCommand('copy')
      area.remove()
      return ok
    } catch {
      return false
    }
  }
}

/** Title, who is here (avatars with online dots), copy or share the invite link, and the way back. */
export function RoomHeader({ room, me, onBack, onLeave }: { room: Room; me: Participant | undefined; onBack: () => void; onLeave: () => void }) {
  const [copied, setCopied] = useState<'copied' | 'failed' | null>(null)
  const timer = useRef<number | undefined>(undefined)
  useEffect(() => () => window.clearTimeout(timer.current), [])
  const link = inviteUrl(room.id)
  const canShare = typeof navigator.share === 'function'

  const copy = async () => {
    const ok = await copyText(link)
    setCopied(ok ? 'copied' : 'failed')
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => setCopied(null), 2200)
  }
  const share = async () => {
    try {
      await navigator.share({ title: room.title, text: `Join our plan: ${room.title}`, url: link })
    } catch {
      // Dismissed the share sheet: nothing to do.
    }
  }

  const shown = room.participants.slice(0, 6)
  const online = room.participants.filter((p) => p.online).length

  return (
    <header className="relative flex items-center gap-1 border-b border-line bg-surface px-2 pb-1.5 pt-[max(0.375rem,env(safe-area-inset-top))] sm:px-3">
      <IconButton label="Back to Home" onClick={onBack}>
        <ChevronLeft className="size-6" aria-hidden="true" />
      </IconButton>
      <div className="min-w-0 flex-1">
        <h1 className="t-section truncate" title={room.title}>
          {room.title}
        </h1>
        <div className="flex items-center gap-2">
          <ul className="flex -space-x-1.5" aria-label={`In this room: ${room.participants.map((p) => `${p.name}${p.online ? ', online' : ''}`).join('; ')}`}>
            {shown.map((p) => (
              <li key={p.id} title={`${p.name}${p.online ? ' (online)' : ''}${p.id === me?.id ? ' (you)' : ''}`}>
                <Avatar member={avatarOf(p)} size={26} presence={p.online ? 'online' : undefined} className="rounded-full ring-2 ring-surface" />
              </li>
            ))}
            {room.participants.length > shown.length && (
              <li className="grid size-[26px] place-items-center rounded-full bg-surface-2 text-xs font-bold ring-2 ring-surface" aria-hidden="true">
                +{room.participants.length - shown.length}
              </li>
            )}
          </ul>
          <p className="t-caption truncate">
            {plural(room.participants.length, 'person', 'people')}, {online} here
          </p>
        </div>
      </div>
      {canShare && (
        <IconButton label="Share invite link" onClick={() => void share()}>
          <Share2 className="size-5" aria-hidden="true" />
        </IconButton>
      )}
      <IconButton label={copied === 'copied' ? 'Invite link copied' : 'Copy invite link'} variant={copied === 'copied' ? 'primary' : 'tertiary'} tooltip={false} onClick={() => void copy()}>
        {copied === 'copied' ? <Check className="size-5" aria-hidden="true" /> : <Link2 className="size-5" aria-hidden="true" />}
      </IconButton>
      <IconButton label="Leave room" onClick={onLeave}>
        <LogOut className="size-5" aria-hidden="true" />
      </IconButton>
      <span role="status" aria-live="polite" className="sr-only">
        {copied === 'copied' ? 'Invite link copied' : copied === 'failed' ? 'Could not copy the link' : ''}
      </span>
      {copied && (
        <span className="pointer-events-none absolute right-3 top-14 z-20 rounded-md bg-[var(--rw-neutral-180)] px-2.5 py-1 text-xs font-semibold text-white shadow-md" aria-hidden="true">
          {copied === 'copied' ? 'Link copied' : 'Copy failed: select the address bar instead'}
        </span>
      )}
    </header>
  )
}
