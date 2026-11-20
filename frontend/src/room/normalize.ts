import type { CostCategory, CostSummary, Plan, Room } from '@/types'

const CATEGORIES: CostCategory[] = ['flights', 'transport', 'stay', 'food', 'activities', 'local', 'other']

/** What the summary would be from the cost lines alone, for a server that does not send `plan.cost_summary` (yet). */
function fallbackSummary(plan: Plan): CostSummary {
  const travellers = Math.max(1, plan.travelers.length)
  const by: Record<CostCategory, number> = { flights: 0, transport: 0, stay: 0, food: 0, activities: 0, local: 0, other: 0 }
  for (const c of plan.costs) {
    const cat = CATEGORIES.includes(c.category as CostCategory) ? (c.category as CostCategory) : 'other'
    by[cat] += c.amount
  }
  const total = plan.costs.reduce((s, c) => s + c.amount, 0)
  const days = new Map<number, { day: number; date: string; amount: number }>()
  for (const i of plan.itinerary) {
    if (!i.cost) continue
    const d = days.get(i.day) ?? { day: i.day, date: i.date, amount: 0 }
    d.amount += i.cost
    days.set(i.day, d)
  }
  const budget = plan.budget?.total ?? null
  return {
    total,
    per_person: Math.round(total / travellers),
    travellers,
    currency: plan.budget?.currency ?? 'INR',
    by_category: by,
    by_day: [...days.values()].sort((a, b) => a.day - b.day),
    budget,
    remaining: budget === null ? null : budget - total,
    over_budget: budget !== null && total > budget,
  }
}

/** Every list can be empty, and an older server may not know the newer fields: fill them in so the screens never meet `undefined`. */
export function normalizeRoom<T extends Room>(room: T): T {
  const p = room.plan as Partial<Plan> & Record<string, unknown>
  const plan: Plan = {
    goal: p.goal ?? '',
    destination: p.destination ?? null,
    origin: p.origin ?? null,
    dates: p.dates ?? null,
    travelers: p.travelers ?? [],
    budget: p.budget ?? null,
    preferences: p.preferences ?? [],
    flights: p.flights ?? [],
    transport: p.transport ?? [],
    local_mode: p.local_mode ?? null,
    hotels: p.hotels ?? [],
    itinerary: p.itinerary ?? [],
    places: p.places ?? [],
    restaurants: p.restaurants ?? [],
    costs: p.costs ?? [],
    cost_summary: undefined as unknown as CostSummary,
    decisions: p.decisions ?? [],
    open_questions: p.open_questions ?? [],
    checklist: p.checklist ?? [],
  }
  plan.cost_summary = p.cost_summary ?? fallbackSummary(plan)
  return { ...room, plan, participants: room.participants ?? [], messages: room.messages ?? [], bookings: room.bookings ?? [], pending_approval: room.pending_approval ?? null }
}
