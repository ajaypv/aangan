import { CalendarDays, CalendarPlus } from 'lucide-react'
import { useMemo, useState } from 'react'
import { dayLabel } from '@/lib/format'
import { clashesOf, sortEvents, weekFrom } from '@/lib/schedule'
import { useMediaQuery } from '@/lib/useMediaQuery'
import { cn } from '@/lib/utils'
import { useApp } from '@/state/AppState'
import { Avatar, Button, EmptyState, ScreenSkeleton } from '@/ui/primitives'
import { AddEventSheet } from './schedule/AddEventSheet'
import { DayList, DayStrip, FreeDay, WeekGrid } from './schedule/Agenda'
import { EventSheet } from './schedule/EventSheet'

/** Everyone's plans for the next seven days. Phones get a day strip over an agenda; wide screens get one column per day. */
export function ScheduleView() {
  const { snap } = useApp()
  const wide = useMediaQuery('(min-width: 1024px)')
  const [filter, setFilter] = useState<string | null>(null)
  const [picked, setPicked] = useState<string | null>(null)
  const [openId, setOpenId] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)

  const days = useMemo(() => (snap ? weekFrom(snap.now.date) : []), [snap])
  const visible = useMemo(() => (snap ? snap.calendar.filter((e) => !filter || e.member_ids.includes(filter)) : []), [snap, filter])

  if (!snap) return <ScreenSkeleton />

  const eventsOn = (date: string) => sortEvents(visible.filter((e) => e.date === date))
  const clashOn = (date: string) => eventsOn(date).some((e) => clashesOf(e, snap.calendar).length > 0)
  const selected = picked && days.includes(picked) ? picked : snap.now.date
  const weekCount = days.reduce((n, d) => n + eventsOn(d).length, 0)
  const open = openId ? (snap.calendar.find((e) => e.id === openId) ?? null) : null
  const child = snap.members.find((m) => m.kind === 'child') ?? snap.members[0]
  const filterName = filter ? snap.members.find((m) => m.id === filter)?.name : null

  return (
    <div className="mx-auto w-full max-w-6xl px-4 pb-8 pt-4 lg:px-8">
      <div className="mb-4 flex items-end justify-between gap-3">
        <div className="min-w-0">
          <h2 className="t-section">This week</h2>
          <p className="t-secondary">Everyone’s plans, starting today</p>
        </div>
        <Button icon={<CalendarPlus className="size-4" aria-hidden="true" />} onClick={() => setAdding(true)}>
          Add event
        </Button>
      </div>

      {snap.members.length >= 3 && (
        <div className="-mx-4 mb-4 flex gap-2 overflow-x-auto px-4 pb-1 lg:mx-0 lg:px-0" role="group" aria-label="Show whose events">
          <button
            type="button"
            aria-pressed={filter === null}
            onClick={() => setFilter(null)}
            className={cn(
              'inline-flex min-h-11 shrink-0 items-center rounded-full border px-4 text-sm font-semibold transition-colors lg:min-h-9',
              filter === null ? 'border-[var(--selected-edge)] bg-brand-soft text-brand-text' : 'border-edge bg-surface text-ink-2 hover:bg-hover',
            )}
          >
            Everyone
          </button>
          {snap.members.map((m) => (
            <button
              key={m.id}
              type="button"
              aria-pressed={filter === m.id}
              onClick={() => setFilter(filter === m.id ? null : m.id)}
              className={cn(
                'inline-flex min-h-11 shrink-0 items-center gap-2 rounded-full border py-1 pl-1.5 pr-3.5 text-sm font-semibold transition-colors lg:min-h-9',
                filter === m.id ? 'border-[var(--selected-edge)] bg-brand-soft text-brand-text' : 'border-edge bg-surface text-ink-2 hover:bg-hover',
              )}
            >
              <Avatar member={m} size={26} />
              {m.name}
            </button>
          ))}
        </div>
      )}

      {weekCount === 0 ? (
        <EmptyState
          icon={<CalendarDays className="size-6" aria-hidden="true" />}
          title="Nothing scheduled"
          action={
            <Button icon={<CalendarPlus className="size-4" aria-hidden="true" />} onClick={() => setAdding(true)}>
              Add an event
            </Button>
          }
        >
          {filterName ? `${filterName} has nothing planned this week.` : 'The next seven days are free.'}
          {child && (
            <>
              {' '}
              Or ask Aangan. Try: <span className="font-semibold text-ink">“Add a dentist appointment for {child.name} on Saturday at 5 pm”</span>.
            </>
          )}
        </EmptyState>
      ) : wide ? (
        <WeekGrid snap={snap} days={days} eventsOn={eventsOn} onOpen={setOpenId} />
      ) : (
        <>
          <DayStrip
            snap={snap}
            days={days}
            selected={selected}
            countOn={(d) => eventsOn(d).length}
            clashOn={clashOn}
            onSelect={setPicked}
          />
          <section id="day-agenda" role="tabpanel" aria-labelledby={`day-${selected}`} className="mt-4">
            <h3 className="t-card mb-2">{selected === snap.now.date ? `Today, ${dayLabel(selected)}` : dayLabel(selected)}</h3>
            {eventsOn(selected).length === 0 ? (
              <FreeDay date={selected} today={selected === snap.now.date} />
            ) : (
              <DayList snap={snap} events={eventsOn(selected)} date={selected} onOpen={setOpenId} />
            )}
          </section>
        </>
      )}

      <EventSheet snap={snap} event={open} onClose={() => setOpenId(null)} />
      <AddEventSheet snap={snap} open={adding} defaultDate={selected} onClose={() => setAdding(false)} />
    </div>
  )
}
