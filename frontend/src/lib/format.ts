import type { CalendarEvent, Member, Snapshot } from '@/types'

export const AGENT_META: Record<string, { label: string; color: string }> = {
  travel: { label: 'Travel', color: 'var(--agent-travel)' },
  calendar: { label: 'Calendar', color: 'var(--agent-calendar)' },
  dining: { label: 'Dining', color: 'var(--agent-dining)' },
  school: { label: 'School', color: 'var(--agent-school)' },
  care: { label: 'Care', color: 'var(--agent-care)' },
  household: { label: 'Household', color: 'var(--agent-household)' },
  money: { label: 'Money', color: 'rgb(var(--rw-dvt-3))' },
  orchestrator: { label: 'Aangan', color: 'var(--agent-orchestrator)' },
  aangan: { label: 'Aangan', color: 'var(--agent-orchestrator)' },
}

export const agentMeta = (name: string | null | undefined) =>
  AGENT_META[name ?? 'aangan'] ?? { label: name ? name[0].toUpperCase() + name.slice(1) : 'Aangan', color: 'var(--agent-orchestrator)' }

export const initials = (name: string) => name.trim().slice(0, 1).toUpperCase()

export const memberOf = (snap: Snapshot, id: string): Member | undefined => snap.members.find((m) => m.id === id)

const WEEKDAY = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MONTH = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

const parts = (iso: string) => {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d))
}

export const weekdayShort = (iso: string) => WEEKDAY[parts(iso).getUTCDay()]
export const dayNumber = (iso: string) => parts(iso).getUTCDate()
export const monthShort = (iso: string) => MONTH[parts(iso).getUTCMonth()]
export const dayLabel = (iso: string) => `${weekdayShort(iso)} ${dayNumber(iso)} ${monthShort(iso)}`

export const addDays = (iso: string, n: number) => {
  const d = parts(iso)
  d.setUTCDate(d.getUTCDate() + n)
  return d.toISOString().slice(0, 10)
}

/** The days shown in the week view: the demo "today" and the four after it. */
export const weekDates = (today: string, days = 5) => Array.from({ length: days }, (_, i) => addDays(today, i))

export const minutes = (hhmm: string) => {
  const [h, m] = hhmm.split(':').map(Number)
  return h * 60 + m
}

export const timeRange = (e: Pick<CalendarEvent, 'start' | 'end'>) => `${e.start} to ${e.end}`

export const eventsOn = (snap: Snapshot, date: string, memberId?: string) =>
  snap.calendar
    .filter((e) => e.date === date && (!memberId || e.member_ids.includes(memberId)))
    .sort((a, b) => a.start.localeCompare(b.start))

export const joinNames = (snap: Snapshot, ids: string[]) =>
  ids.map((id) => memberOf(snap, id)?.name ?? id).join(', ')

export const sentenceCase = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s)

/** Starter prompts shown as chips. They are things a person might say, not data. */
export function suggestionsFor(member: Member): string[] {
  const byId: Record<string, string[]> = {
    priya: [
      'Sunday ko sab saath lunch pe jaana hai',
      'When is everyone free on Sunday?',
      'How is Aarav doing in school?',
      'Book flights for all of us to Goa on 26 Dec',
      'Meet my daughter Anaya, she is 6 and allergic to eggs',
    ],
    rahul: ['My flight is delayed, find me an alternative', 'Did Dadi take her medicines?', 'What is on my calendar tomorrow?'],
    aarav: ['Main school pahunch gaya', 'Aaj maths mein 42 out of 50 mila', 'Homework ho gaya'],
    dadi: ['Dawai le li', 'Meri dawai khatam ho rahi hai', 'Mujhe thoda chakkar aa raha hai'],
  }
  if (byId[member.id]) return byId[member.id]
  if (member.kind === 'child') return ['I reached school', 'I got 40 out of 50 in maths', 'Homework is done']
  if (member.kind === 'senior') return ['I took my medicine', 'My medicine is running out']
  return ['When is everyone free this weekend?', 'What is on my calendar tomorrow?', 'Remember that I like spicy food']
}
