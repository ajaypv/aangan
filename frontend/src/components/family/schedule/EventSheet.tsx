import { MapPin, TriangleAlert } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { dayLabel, minutes } from '@/lib/format'
import { clashesOf, kindOf } from '@/lib/schedule'
import { useApp } from '@/state/AppState'
import type { CalendarEvent, Snapshot } from '@/types'
import { Avatar, Button, Field, Pill, inputClass } from '@/ui/primitives'
import { Sheet } from '@/ui/Sheet'
import { eventMembers } from './EventItem'

const SOURCE_NOTE: Record<string, string> = {
  calendar: 'Added to the calendar',
  dining: 'Booked by Dining',
  care: 'Booked by Care',
  travel: 'Booked by Travel',
  school: 'Added by School',
}

const hhmm = (mins: number) => `${String(Math.floor(mins / 60) % 24).padStart(2, '0')}:${String(mins % 60).padStart(2, '0')}`

function Details({ snap, event, onClose }: { snap: Snapshot; event: CalendarEvent; onClose: () => void }) {
  const { callTool, busy } = useApp()
  const [mode, setMode] = useState<'view' | 'move' | 'cancel'>('view')
  const [date, setDate] = useState(event.date)
  const [start, setStart] = useState(event.start)
  const members = eventMembers(snap, event)
  const kind = kindOf(event)
  const KindIcon = kind.icon
  const clashes = clashesOf(event, snap.calendar)
  const length = minutes(event.end) - minutes(event.start)
  const unchanged = date === event.date && start === event.start

  const move = async (e: FormEvent) => {
    e.preventDefault()
    const ok = await callTool('calendar', 'move_event', { event_id: event.id, date, start }, 'Event moved.')
    if (ok) setMode('view')
  }
  const cancel = async () => {
    const ok = await callTool('calendar', 'cancel_event', { event_id: event.id }, 'Event cancelled.')
    if (ok) onClose()
  }

  return (
    <div className="space-y-4 text-sm">
      <div>
        <p className="num text-base font-semibold">
          {dayLabel(event.date)}, {event.start} to {event.end}
        </p>
        {event.location && (
          <p className="t-secondary mt-1 flex items-center gap-1.5">
            <MapPin className="size-4" aria-hidden="true" />
            {event.location}
          </p>
        )}
      </div>

      <ul className="flex flex-wrap gap-2" aria-label="People">
        {members.map((m) => (
          <li key={m.id} className="inline-flex items-center gap-1.5 rounded-full bg-surface-2 py-1 pl-1 pr-3 font-semibold">
            <Avatar member={m} size={24} /> {m.name}
          </li>
        ))}
      </ul>

      <div className="flex flex-wrap gap-2">
        <Pill>
          <KindIcon className="size-3" aria-hidden="true" />
          {kind.label}
        </Pill>
        {event.source && event.source !== 'seed' && <Pill tone="brand">{SOURCE_NOTE[event.source] ?? `Added by ${event.source}`}</Pill>}
      </div>

      {clashes.length > 0 && (
        <ul className="space-y-1.5" aria-label="Clashes">
          {clashes.map((c) => (
            <li key={c.id} className="flex items-start gap-2 rounded-md bg-warning-bg px-3 py-2 text-[var(--rw-text-warning)]">
              <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              <span>
                Overlaps with <strong>{c.title}</strong> ({c.start} to {c.end}) for {eventMembers(snap, c).filter((m) => event.member_ids.includes(m.id)).map((m) => m.name).join(', ')}.
              </span>
            </li>
          ))}
        </ul>
      )}

      {mode === 'view' && (
        <div className="flex flex-wrap gap-2 pt-1">
          <Button variant="secondary" onClick={() => setMode('move')}>
            Move
          </Button>
          <Button variant="tertiary" className="text-[var(--rw-text-danger)]" onClick={() => setMode('cancel')}>
            Cancel event
          </Button>
        </div>
      )}

      {mode === 'move' && (
        <form onSubmit={move} className="space-y-3 rounded-lg border border-line p-3">
          <p className="font-semibold">Move to another time</p>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Date">
              <input required type="date" min={snap.now.date} className={inputClass} value={date} onChange={(e) => setDate(e.target.value)} />
            </Field>
            <Field label="Starts at">
              <input required type="time" className={inputClass} value={start} onChange={(e) => setStart(e.target.value)} />
            </Field>
          </div>
          <p className="t-caption">It keeps its length of {length} minutes and ends at {start ? hhmm(minutes(start) + length) : event.end}. Everyone involved is told.</p>
          <div className="flex justify-end gap-2">
            <Button variant="tertiary" onClick={() => setMode('view')}>
              Back
            </Button>
            <Button type="submit" loading={busy} disabled={unchanged || !date || !start}>
              Move event
            </Button>
          </div>
        </form>
      )}

      {mode === 'cancel' && (
        <div className="space-y-3 rounded-lg border border-[var(--rw-danger)] bg-danger-bg p-3" role="alertdialog" aria-label="Confirm cancelling">
          <p className="font-semibold">Cancel “{event.title}”?</p>
          <p className="t-secondary">It leaves the calendar for {members.map((m) => m.name).join(', ')}, and they are told.</p>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setMode('view')}>
              Keep it
            </Button>
            <Button variant="danger" loading={busy} onClick={cancel}>
              Yes, cancel event
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

/** Details of one event, with Move and Cancel (both go through the calendar agent's tools and notify the people involved). */
export function EventSheet({ snap, event, onClose }: { snap: Snapshot; event: CalendarEvent | null; onClose: () => void }) {
  return (
    <Sheet open={event !== null} title={event?.title ?? ''} onClose={onClose}>
      {event && <Details key={event.id} snap={snap} event={event} onClose={onClose} />}
    </Sheet>
  )
}
