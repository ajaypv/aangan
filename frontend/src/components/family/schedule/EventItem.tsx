import { MapPin, TriangleAlert } from 'lucide-react'
import { memberOf } from '@/lib/format'
import { isOngoing, kindOf } from '@/lib/schedule'
import { cn } from '@/lib/utils'
import type { CalendarEvent, Member, Snapshot } from '@/types'
import { MemberDots, Pill } from '@/ui/primitives'

export function eventMembers(snap: Snapshot, event: CalendarEvent): Member[] {
  return event.member_ids.map((id) => memberOf(snap, id)).filter((m): m is Member => m !== undefined)
}

interface Props {
  snap: Snapshot
  event: CalendarEvent
  clashes: CalendarEvent[]
  /** row: the mobile agenda. card: a compact tile in a desktop day column. */
  variant?: 'row' | 'card'
  showNow?: boolean
  onOpen: () => void
}

/** One event as a list item. Kind is a small icon, never a loud colour; people are identity dots. */
export function EventItem({ snap, event, clashes, variant = 'row', showNow = false, onOpen }: Props) {
  const members = eventMembers(snap, event)
  const kind = kindOf(event)
  const KindIcon = kind.icon
  const ongoing = showNow && isOngoing(event, snap.now.time)
  const label = [
    `${event.title}, ${event.start} to ${event.end}`,
    event.location,
    members.map((m) => m.name).join(', '),
    clashes.length ? `overlaps with ${clashes.map((c) => c.title).join(', ')}` : '',
  ]
    .filter(Boolean)
    .join(', ')

  if (variant === 'card') {
    return (
      <li>
        <button
          type="button"
          onClick={onOpen}
          aria-label={label}
          className={cn(
            'block w-full rounded-lg border bg-surface p-2.5 text-left shadow-xs transition-colors hover:bg-hover',
            ongoing ? 'border-[var(--selected-edge)] bg-brand-soft' : 'border-line',
          )}
        >
          <span className="num flex items-center justify-between gap-2 text-xs font-bold text-ink-2">
            {event.start} to {event.end}
            <KindIcon className="size-3.5 shrink-0" aria-hidden="true" />
          </span>
          <span className="mt-0.5 block text-sm font-semibold leading-snug">{event.title}</span>
          <span className="mt-1.5 flex items-center justify-between gap-2">
            <MemberDots members={members} />
            {clashes.length > 0 && <TriangleAlert className="size-4 text-[var(--rw-warning)]" aria-hidden="true" />}
          </span>
        </button>
      </li>
    )
  }

  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        aria-label={label}
        className={cn(
          'flex w-full items-stretch gap-3 rounded-xl border bg-surface px-3 py-3 text-left shadow-xs transition-colors hover:bg-hover',
          ongoing ? 'border-[var(--selected-edge)] bg-brand-soft' : 'border-line',
        )}
      >
        <span className="num w-14 shrink-0 text-right">
          <span className="block text-sm font-bold">{event.start}</span>
          <span className="t-caption block">{event.end}</span>
        </span>
        <span aria-hidden="true" className="w-px shrink-0 bg-line" />
        <span className="min-w-0 flex-1">
          <span className="flex items-start justify-between gap-2">
            <span className="block font-semibold leading-snug">{event.title}</span>
            {ongoing && <Pill tone="brand">Now</Pill>}
          </span>
          {event.location && (
            <span className="t-secondary mt-0.5 flex items-center gap-1">
              <MapPin className="size-3.5 shrink-0" aria-hidden="true" />
              <span className="truncate">{event.location}</span>
            </span>
          )}
          <span className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <span className="t-caption inline-flex items-center gap-1">
              <KindIcon className="size-3.5" aria-hidden="true" />
              {kind.label}
            </span>
            <MemberDots members={members} />
            {clashes.length > 0 && (
              <Pill tone="warning">
                <TriangleAlert className="size-3" aria-hidden="true" />
                Clash with {clashes[0].title}
                {clashes.length > 1 ? ` +${clashes.length - 1}` : ''}
              </Pill>
            )}
          </span>
        </span>
      </button>
    </li>
  )
}

/** A thin line with the time, placed where "now" falls in today's list. */
export function NowMarker({ time }: { time: string }) {
  return (
    <li aria-label={`Now, ${time}`} className="flex items-center gap-2 py-0.5 text-xs font-bold text-brand-text">
      <span aria-hidden="true" className="size-2 rounded-full bg-brand" />
      <span className="num">Now {time}</span>
      <span aria-hidden="true" className="h-px flex-1 bg-brand" />
    </li>
  )
}
