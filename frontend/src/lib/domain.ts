import { minutes } from '@/lib/format'
import type { CalendarEvent, CareSenior, Mark, MemoryFact, SchoolKid, Snapshot } from '@/types'

export const kidOf = (snap: Snapshot, id: string): SchoolKid | undefined => snap.domains.school?.kids?.[id]
export const seniorOf = (snap: Snapshot, id: string): CareSenior | undefined => snap.domains.care?.seniors?.[id]
/** Today's school event for a child. Without one, nobody has set school up, so "not at school" must never be raised. */
export const schoolToday = (snap: Snapshot, id: string): CalendarEvent | undefined =>
  snap.calendar.find((e) => e.kind === 'school' && e.member_ids.includes(id) && e.date === snap.now.date)

export const factsOf = (snap: Snapshot, id: string): MemoryFact[] => snap.memory.filter((f) => f.about === id)
export const familyFacts = (snap: Snapshot): MemoryFact[] => factsOf(snap, 'family')

export const pct = (m: Pick<Mark, 'score' | 'max'>) => Math.round((100 * m.score) / m.max)

export interface SubjectTrend {
  subject: string
  latest: Mark
  delta: number | null
}

/** The latest mark in each subject and how it moved against the one before it. */
export function marksBySubject(kid: SchoolKid): SubjectTrend[] {
  const bySubject = new Map<string, Mark[]>()
  for (const m of [...kid.marks].sort((a, b) => a.date.localeCompare(b.date))) {
    bySubject.set(m.subject, [...(bySubject.get(m.subject) ?? []), m])
  }
  return [...bySubject.entries()].map(([subject, list]) => {
    const latest = list[list.length - 1]
    const prev = list.length > 1 ? list[list.length - 2] : null
    return { subject, latest, delta: prev ? pct(latest) - pct(prev) : null }
  })
}

export const marksInOrder = (kid: SchoolKid): Mark[] => [...kid.marks].sort((a, b) => a.date.localeCompare(b.date))

export interface Dose {
  med: string
  dose: string
  slot: string
  status: 'taken' | 'due' | 'missed' | 'upcoming'
  takenAt?: string
}

/** Today's doses, using how the care agent records them: med.taken["YYYY-MM-DD HH:MM"] = the time it was logged. */
export function dosesToday(snap: Snapshot, senior: CareSenior): Dose[] {
  const today = snap.now.date
  const now = minutes(snap.now.time)
  const doses: Dose[] = []
  for (const med of senior.meds) {
    for (const slot of med.times) {
      const takenAt = med.taken[`${today} ${slot}`] as string | undefined
      let status: Dose['status'] = 'upcoming'
      if (takenAt) status = 'taken'
      else if (minutes(slot) + 120 < now) status = 'missed'
      else if (minutes(slot) <= now) status = 'due'
      doses.push({ med: med.name, dose: med.dose, slot, status, takenAt })
    }
  }
  return doses.sort((a, b) => a.slot.localeCompare(b.slot))
}

export function nextEvents(snap: Snapshot, memberId: string, count = 3): CalendarEvent[] {
  const nowKey = `${snap.now.date} ${snap.now.time}`
  return snap.calendar
    .filter((e) => e.member_ids.includes(memberId) && `${e.date} ${e.end}` >= nowKey)
    .sort((a, b) => `${a.date} ${a.start}`.localeCompare(`${b.date} ${b.start}`))
    .slice(0, count)
}

export function factTone(f: MemoryFact): 'bad' | 'warn' | 'neutral' {
  if (f.tags.includes('allergy')) return 'bad'
  if (f.tags.includes('access') || f.tags.includes('health')) return 'warn'
  return 'neutral'
}
