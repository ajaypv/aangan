import { BookmarkPlus, CalendarDays, GraduationCap, HeartPulse, Plane, UtensilsCrossed, Wallet, type LucideIcon } from 'lucide-react'
import type { Member, Snapshot } from '@/types'

export interface Capability {
  id: string
  title: string
  /** What tapping the card says to Aangan. */
  phrase: string
  icon: LucideIcon
}

const first = (m: Member) => m.name.trim().split(/\s+/)[0]
const her = (m: Member) => (m.gender === 'female' ? 'her' : m.gender === 'male' ? 'his' : 'their')

/**
 * The starter cards on an empty conversation. They depend on who is in the household: school prompts only when there is a child,
 * care prompts only when there is a senior, and every example uses real names. Never more than six.
 */
export function capabilityCards(snap: Snapshot, me: Member): Capability[] {
  const others = snap.members.filter((m) => m.id !== me.id)
  const alone = snap.members.length <= 1
  const child = snap.members.find((m) => m.kind === 'child')
  const senior = snap.members.find((m) => m.kind === 'senior')
  const cards: Capability[] = []

  cards.push({
    id: 'outing',
    title: 'Plan an outing',
    phrase: alone ? 'Find me a restaurant for lunch on Sunday' : "Let's all go out for lunch on Sunday",
    icon: UtensilsCrossed,
  })

  if (child) {
    cards.push({
      id: 'school',
      title: 'School updates',
      phrase: me.id === child.id ? 'I reached school' : `How is ${first(child)} doing in school?`,
      icon: GraduationCap,
    })
  }

  if (senior) {
    cards.push({
      id: 'care',
      title: 'Check on care',
      phrase: me.id === senior.id ? 'I took my medicine' : `Did ${first(senior)} take ${her(senior)} medicines today?`,
      icon: HeartPulse,
    })
  }

  cards.push({
    id: 'schedule',
    title: 'Check the schedule',
    phrase: alone || others.length === 0 ? 'What is on my calendar tomorrow?' : 'When is everyone free on Sunday?',
    icon: CalendarDays,
  })

  cards.push({ id: 'spending', title: 'Track spending', phrase: 'I spent 450 on groceries', icon: Wallet })

  cards.push({
    id: 'trip',
    title: 'Plan a trip',
    phrase: alone ? 'Book a flight to Goa on 26 Dec' : 'Book flights for all of us to Goa on 26 Dec',
    icon: Plane,
  })

  cards.push({ id: 'remember', title: 'Remember something', phrase: "Remember that I don't like mushrooms", icon: BookmarkPlus })

  return cards.slice(0, 6)
}
