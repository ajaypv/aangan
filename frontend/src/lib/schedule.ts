import { Briefcase, CalendarDays, Dumbbell, GraduationCap, Plane, Stethoscope, UtensilsCrossed, type LucideIcon } from 'lucide-react'
import { addDays, minutes } from '@/lib/format'
import type { CalendarEvent } from '@/types'

export const WEEK_LENGTH = 7

/** Today and the six days after it. */
export const weekFrom = (today: string) => Array.from({ length: WEEK_LENGTH }, (_, i) => addDays(today, i))

export interface KindInfo {
  label: string
  icon: LucideIcon
}

const KINDS: Record<string, KindInfo> = {
  event: { label: 'Event', icon: CalendarDays },
  work: { label: 'Work', icon: Briefcase },
  school: { label: 'School', icon: GraduationCap },
  activity: { label: 'Activity', icon: Dumbbell },
  dining: { label: 'Dining', icon: UtensilsCrossed },
  travel: { label: 'Travel', icon: Plane },
  health: { label: 'Health', icon: Stethoscope },
}

/** The kinds a person can pick when adding an event. */
export const KIND_OPTIONS = ['event', 'work', 'school', 'activity', 'dining', 'travel', 'health'] as const

/** Events made by the dining, care or travel agents carry a source even when their kind is generic. */
const SOURCE_KIND: Record<string, string> = { dining: 'dining', care: 'health', travel: 'travel' }

export function kindOf(e: Pick<CalendarEvent, 'kind' | 'source'>): KindInfo {
  return KINDS[e.kind] ?? KINDS[SOURCE_KIND[e.source] ?? ''] ?? KINDS.event
}

export const kindLabel = (kind: string) => (KINDS[kind] ?? KINDS.event).label

/** Other events on the same day that overlap this one for at least one shared person. */
export function clashesOf(e: CalendarEvent, all: CalendarEvent[]): CalendarEvent[] {
  const s = minutes(e.start)
  const f = minutes(e.end)
  return all.filter(
    (o) => o.id !== e.id && o.date === e.date && o.member_ids.some((id) => e.member_ids.includes(id)) && minutes(o.start) < f && s < minutes(o.end),
  )
}

export const isOngoing = (e: CalendarEvent, nowHHMM: string) => minutes(e.start) <= minutes(nowHHMM) && minutes(nowHHMM) < minutes(e.end)

/** Index of the first event that has not started yet, where a "now" marker belongs. Equals the list length when all have started. */
export const nowIndex = (events: CalendarEvent[], nowHHMM: string) => {
  const idx = events.findIndex((e) => minutes(e.start) > minutes(nowHHMM))
  return idx === -1 ? events.length : idx
}

export const sortEvents = (events: CalendarEvent[]) => [...events].sort((a, b) => a.start.localeCompare(b.start) || a.end.localeCompare(b.end))
