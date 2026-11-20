import { useState, type FormEvent } from 'react'
import { minutes } from '@/lib/format'
import { KIND_OPTIONS, kindLabel } from '@/lib/schedule'
import { useApp } from '@/state/AppState'
import type { Snapshot } from '@/types'
import { Button, Field, inputClass } from '@/ui/primitives'
import { Sheet } from '@/ui/Sheet'
import { MemberPicker } from './MemberPicker'

const hhmm = (mins: number) => `${String(Math.min(23, Math.floor(mins / 60))).padStart(2, '0')}:${String(mins % 60).padStart(2, '0')}`

/** The next whole hour after "now", kept in the day. */
const nextHour = (now: string) => Math.min(22 * 60, (Math.floor(minutes(now) / 60) + 1) * 60)

function Form({ snap, defaultDate, onDone }: { snap: Snapshot; defaultDate: string; onDone: () => void }) {
  const { callTool, busy, me } = useApp()
  const [title, setTitle] = useState('')
  const [who, setWho] = useState<string[]>(me ? [me] : snap.members.map((m) => m.id))
  const [date, setDate] = useState(defaultDate)
  const [start, setStart] = useState(hhmm(nextHour(snap.now.time)))
  const [end, setEnd] = useState(hhmm(nextHour(snap.now.time) + 60))
  const [location, setLocation] = useState('')
  const [kind, setKind] = useState<string>('event')

  const endsAfterStart = minutes(end) > minutes(start)
  const problem = !title.trim() ? 'Give the event a name.' : who.length === 0 ? 'Choose at least one person.' : !endsAfterStart ? 'The end time must be after the start time.' : null

  // Moving the start keeps the length of the event.
  const changeStart = (next: string) => {
    if (next) setEnd(hhmm(Math.min(23 * 60 + 59, minutes(next) + (minutes(end) - minutes(start)))))
    setStart(next)
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (problem) return
    const ok = await callTool(
      'calendar',
      'create_event',
      { member_ids: who, title: title.trim(), date, start, end, ...(location.trim() ? { location: location.trim() } : {}), kind },
      `${title.trim()} added.`,
    )
    if (ok) onDone()
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <Field label="What is it?">
        <input required className={inputClass} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Dentist appointment" autoComplete="off" />
      </Field>
      <MemberPicker legend="Who is involved?" members={snap.members} value={who} onChange={setWho} />
      <div className="grid grid-cols-3 gap-3">
        <Field label="Date">
          <input required type="date" min={snap.now.date} className={inputClass} value={date} onChange={(e) => setDate(e.target.value)} />
        </Field>
        <Field label="Starts">
          <input required type="time" className={inputClass} value={start} onChange={(e) => changeStart(e.target.value)} />
        </Field>
        <Field label="Ends">
          <input required type="time" className={inputClass} value={end} onChange={(e) => setEnd(e.target.value)} />
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Where (optional)">
          <input className={inputClass} value={location} onChange={(e) => setLocation(e.target.value)} autoComplete="off" />
        </Field>
        <Field label="Type">
          <select className={inputClass} value={kind} onChange={(e) => setKind(e.target.value)}>
            {KIND_OPTIONS.map((k) => (
              <option key={k} value={k}>
                {kindLabel(k)}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <p className="t-caption" role={problem ? 'status' : undefined}>
        {problem ?? 'Everyone you choose is told about it.'}
      </p>
      <div className="flex justify-end gap-2 pt-1">
        <Button variant="tertiary" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" loading={busy} disabled={problem !== null}>
          Add event
        </Button>
      </div>
    </form>
  )
}

export function AddEventSheet({ snap, open, defaultDate, onClose }: { snap: Snapshot; open: boolean; defaultDate: string; onClose: () => void }) {
  return (
    <Sheet open={open} title="Add an event" onClose={onClose}>
      <Form snap={snap} defaultDate={defaultDate} onDone={onClose} />
    </Sheet>
  )
}
