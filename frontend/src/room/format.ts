import { dayLabel, dayNumber, monthShort } from '@/lib/format'
import type { Participant, Room } from '@/types'

/** Whole rupees (or the plan's currency) with Indian digit grouping: 16,800 becomes ₹16,800, 1,60,000 stays readable. */
export function money(value: number, currency = 'INR'): string {
  try {
    return new Intl.NumberFormat('en-IN', { style: 'currency', currency, maximumFractionDigits: 0 }).format(value)
  } catch {
    return `${currency} ${Math.round(value)}`
  }
}

const daysBetween = (a: string, b: string) => {
  const [y1, m1, d1] = a.split('-').map(Number)
  const [y2, m2, d2] = b.split('-').map(Number)
  return Math.round((Date.UTC(y2, m2 - 1, d2) - Date.UTC(y1, m1 - 1, d1)) / 86_400_000)
}

/** Nights between two dates (26 to 30 Dec is 4 nights). At least 1. */
export const nights = (start: string, end: string) => Math.max(1, daysBetween(start, end))
/** Days of the trip, both ends included. */
export const tripDays = (start: string, end: string) => Math.max(1, daysBetween(start, end) + 1)

/** "26 to 30 Dec 2026", "28 Dec to 2 Jan 2027", or one date when the trip is a single day. */
export function dateRange(start: string, end: string): string {
  const [ys, ye] = [start.slice(0, 4), end.slice(0, 4)]
  if (start === end) return `${dayNumber(start)} ${monthShort(start)} ${ys}`
  if (monthShort(start) === monthShort(end) && ys === ye) return `${dayNumber(start)} to ${dayNumber(end)} ${monthShort(end)} ${ye}`
  if (ys === ye) return `${dayNumber(start)} ${monthShort(start)} to ${dayNumber(end)} ${monthShort(end)} ${ye}`
  return `${dayNumber(start)} ${monthShort(start)} ${ys} to ${dayNumber(end)} ${monthShort(end)} ${ye}`
}

export { dayLabel }

const toMinutes = (hhmm: string) => {
  const [h, m] = hhmm.split(':').map(Number)
  return h * 60 + m
}

/** "1h 20m" from two clock times; an arrival that looks earlier than the departure is the next day. */
export function durationLabel(dep: string, arr: string): string {
  if (!/^\d{1,2}:\d{2}$/.test(dep) || !/^\d{1,2}:\d{2}$/.test(arr)) return ''
  let diff = toMinutes(arr) - toMinutes(dep)
  if (diff < 0) diff += 24 * 60
  const h = Math.floor(diff / 60)
  const m = diff % 60
  return h ? (m ? `${h}h ${m}m` : `${h}h`) : `${m}m`
}

export const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`

export const participantById = (room: Room, id: string | null | undefined): Participant | undefined =>
  id ? room.participants.find((p) => p.id === id) : undefined

/** The shape the shared Avatar wants. A person with a profile keeps the same colour as everywhere else in the app. */
export const avatarOf = (p: Pick<Participant, 'id' | 'name' | 'member_id'>) => ({ id: p.member_id ?? p.id, name: p.name })

/** A name for a participant id, a plain name (Aangan writes `asked_by` as text), or the id itself. */
export const nameFor = (room: Room, idOrName: string): string => participantById(room, idOrName)?.name ?? idOrName

export const joinList = (names: string[]) => (names.length <= 1 ? (names[0] ?? '') : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`)
