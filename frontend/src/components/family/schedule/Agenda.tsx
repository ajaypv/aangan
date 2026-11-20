import { CalendarCheck } from 'lucide-react'
import { Fragment } from 'react'
import { dayLabel, dayNumber, weekdayShort } from '@/lib/format'
import { clashesOf, nowIndex } from '@/lib/schedule'
import { cn } from '@/lib/utils'
import type { CalendarEvent, Snapshot } from '@/types'
import { EventItem, NowMarker } from './EventItem'

interface DayProps {
  snap: Snapshot
  /** The events of this one day, sorted. */
  events: CalendarEvent[]
  date: string
  variant?: 'row' | 'card'
  onOpen: (id: string) => void
}

/** The events of one day as a list, with a marker at the current time on today. */
export function DayList({ snap, events, date, variant = 'row', onOpen }: DayProps) {
  const today = date === snap.now.date
  const marker = today && events.length > 0 ? nowIndex(events, snap.now.time) : -1
  return (
    <ul className={cn(variant === 'card' ? 'space-y-2' : 'space-y-2.5')}>
      {events.map((e, i) => (
        <Fragment key={e.id}>
          {marker === i && <NowMarker time={snap.now.time} />}
          <EventItem snap={snap} event={e} clashes={clashesOf(e, snap.calendar)} variant={variant} showNow={today} onOpen={() => onOpen(e.id)} />
        </Fragment>
      ))}
      {marker === events.length && marker > 0 && <NowMarker time={snap.now.time} />}
    </ul>
  )
}

/** A free day: calm, not an error. */
export function FreeDay({ date, today }: { date: string; today: boolean }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-dashed border-edge px-4 py-6 text-ink-2">
      <CalendarCheck className="size-5 shrink-0" aria-hidden="true" />
      <p className="t-secondary">{today ? 'Nothing planned for the rest of today.' : `Nothing planned on ${dayLabel(date)}.`}</p>
    </div>
  )
}

/** Mobile: pick a day from the strip. Roving selection with the arrow keys. */
export function DayStrip({
  snap,
  days,
  selected,
  countOn,
  clashOn,
  onSelect,
}: {
  snap: Snapshot
  days: string[]
  selected: string
  countOn: (date: string) => number
  clashOn: (date: string) => boolean
  onSelect: (date: string) => void
}) {
  const move = (delta: number) => {
    const i = days.indexOf(selected)
    const next = days[Math.min(days.length - 1, Math.max(0, i + delta))]
    if (next && next !== selected) onSelect(next)
  }
  return (
    <div
      role="tablist"
      aria-label="Days of the week"
      className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1"
      onKeyDown={(e) => {
        if (e.key === 'ArrowRight') {
          e.preventDefault()
          move(1)
        } else if (e.key === 'ArrowLeft') {
          e.preventDefault()
          move(-1)
        }
      }}
    >
      {days.map((date) => {
        const on = date === selected
        const today = date === snap.now.date
        const count = countOn(date)
        return (
          <button
            key={date}
            id={`day-${date}`}
            role="tab"
            type="button"
            aria-selected={on}
            aria-controls="day-agenda"
            tabIndex={on ? 0 : -1}
            aria-label={`${dayLabel(date)}${today ? ', today' : ''}, ${count === 0 ? 'no events' : count === 1 ? '1 event' : `${count} events`}${clashOn(date) ? ', has a clash' : ''}`}
            onClick={() => onSelect(date)}
            className={cn(
              'flex min-h-[4.25rem] w-14 shrink-0 flex-col items-center justify-center rounded-xl border px-1 py-2 transition-colors',
              on ? 'border-transparent bg-brand text-brand-ink' : today ? 'border-[var(--selected-edge)] bg-brand-soft text-brand-text' : 'border-line bg-surface hover:bg-hover',
            )}
          >
            <span className="text-xs font-semibold">{today ? 'Today' : weekdayShort(date)}</span>
            <span className="num text-lg font-extrabold leading-tight">{dayNumber(date)}</span>
            <span aria-hidden="true" className={cn('mt-0.5 size-1.5 rounded-full', count === 0 ? 'bg-transparent' : clashOn(date) ? 'bg-[var(--rw-warning)]' : on ? 'bg-brand-ink' : 'bg-brand')} />
          </button>
        )
      })}
    </div>
  )
}

/** Desktop: seven columns, one per day. */
export function WeekGrid({
  snap,
  days,
  eventsOn,
  onOpen,
}: {
  snap: Snapshot
  days: string[]
  eventsOn: (date: string) => CalendarEvent[]
  onOpen: (id: string) => void
}) {
  return (
    <div className="grid grid-cols-7 gap-3" aria-label="Week view">
      {days.map((date) => {
        const today = date === snap.now.date
        const events = eventsOn(date)
        return (
          <section key={date} aria-label={dayLabel(date)} className="min-w-0">
            <div className={cn('mb-2 flex items-baseline gap-1.5 rounded-lg px-2.5 py-2', today ? 'bg-brand text-brand-ink' : 'bg-surface-2')}>
              <span className="num text-xl font-extrabold">{dayNumber(date)}</span>
              <span className="text-sm font-semibold">{today ? 'Today' : weekdayShort(date)}</span>
            </div>
            {events.length === 0 ? <p className="t-caption px-1">{today ? 'Nothing planned today' : 'Free'}</p> : <DayList snap={snap} events={events} date={date} variant="card" onOpen={onOpen} />}
          </section>
        )
      })}
    </div>
  )
}
