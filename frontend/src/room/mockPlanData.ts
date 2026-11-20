/* Development-only sample data for the room mock (see mockRoom.ts). */
import type { CostCategory, CostSummary, Flight, Hotel, ItineraryItem, PlaceToVisit, Plan, Restaurant } from '../types'

/** Addendum 1: selected (or else the cheapest proposed) flight x travellers, selected hotel x nights, selected meals and places, and the explicit cost lines. */
export function summarise(p: Plan | null): CostSummary {
  const by: Record<CostCategory, number> = { flights: 0, transport: 0, stay: 0, food: 0, activities: 0, local: 0, other: 0 }
  if (!p) return { total: 0, per_person: 0, travellers: 1, currency: 'INR', by_category: by, by_day: [], budget: null, remaining: null, over_budget: false }
  const n = Math.max(1, p.travelers.length)
  const live = <T extends { status: string }>(xs: T[]) => xs.filter((x) => x.status !== 'rejected')
  const chosen = live(p.flights).filter((f) => f.status === 'selected' || f.status === 'booked')
  const cheapest = [...live(p.flights)].sort((x, y) => x.price - y.price).slice(0, 1)
  for (const f of chosen.length ? chosen : cheapest) by.flights += f.per === 'person' ? f.price * n : f.price
  const nightsN = p.dates ? Math.max(1, Math.round((Date.parse(p.dates.end) - Date.parse(p.dates.start)) / 86_400_000)) : 1
  for (const h of p.hotels.filter((x) => x.status === 'selected' || x.status === 'booked')) by.stay += h.price_per_night * nightsN
  for (const r of p.restaurants.filter((x) => x.status === 'selected')) by.food += Math.round((r.price_for_two * n) / 2)
  for (const x of p.places.filter((y) => y.status === 'selected')) by.activities += x.per === 'person' ? x.price * n : x.price
  for (const c of p.costs) by[(c.category ?? 'other') as CostCategory] += c.amount
  const total = Object.values(by).reduce((a, b) => a + b, 0)
  const days = new Map<number, { day: number; date: string; amount: number }>()
  for (const i of p.itinerary) {
    if (!i.cost) continue
    const d = days.get(i.day) ?? { day: i.day, date: i.date, amount: 0 }
    d.amount += i.cost
    days.set(i.day, d)
  }
  const budget = p.budget?.total ?? null
  return {
    total,
    per_person: Math.round(total / n),
    travellers: n,
    currency: p.budget?.currency ?? 'INR',
    by_category: by,
    by_day: [...days.values()].sort((x, y) => x.day - y.day),
    budget,
    remaining: budget === null ? null : budget - total,
    over_budget: budget !== null && total > budget,
  }
}

export const FLIGHTS: Flight[] = [
  { id: 'f-1', airline: 'IndiGo', number: '6E-512', from: 'BLR', to: 'GOI', date: '2026-12-26', dep: '07:10', arr: '08:30', price: 4200, per: 'person', stops: 0, source: 'live', link: 'https://www.goindigo.in/', status: 'proposed' },
  { id: 'f-2', airline: 'Air India Express', number: 'IX-1134', from: 'BLR', to: 'GOI', date: '2026-12-26', dep: '13:45', arr: '17:05', price: 3650, per: 'person', stops: 1, source: 'sample', link: null, status: 'proposed' },
]

export const HOTELS: Hotel[] = [
  { id: 'h-1', name: 'Coconut Grove Resort', area: 'Candolim', price_per_night: 6500, rating: 4.4, lat: 15.5183, lon: 73.762, step_free: true, source: 'sample', status: 'proposed' },
  { id: 'h-2', name: 'Palm Breeze Beach Stay', area: 'Calangute', price_per_night: 5200, rating: 4.1, lat: 15.5439, lon: 73.7553, step_free: false, source: 'live', status: 'proposed' },
]

export const PLACES: PlaceToVisit[] = [
  { id: 'pl-1', name: 'Basilica of Bom Jesus', area: 'Old Goa', category: 'sight', lat: 15.5009, lon: 73.9116, duration_min: 60, price: 0, per: 'person', day: 2, notes: 'Step-free ramp at the side entrance', source: 'sample', status: 'selected' },
  { id: 'pl-2', name: 'Fort Aguada and lighthouse', area: 'Sinquerim', category: 'sight', lat: 15.4925, lon: 73.7737, duration_min: 90, price: 50, per: 'person', day: 3, notes: 'Short climb, benches along the way', source: 'sample', status: 'selected' },
  { id: 'pl-3', name: 'Baga Beach at sunset', area: 'Baga', category: 'beach', lat: 15.5553, lon: 73.7517, duration_min: 120, price: 0, per: 'person', day: 1, notes: 'Boardwalk near the shacks is step-free', source: 'sample', status: 'selected' },
  { id: 'pl-4', name: 'Anjuna Flea Market', area: 'Anjuna', category: 'market', lat: 15.5733, lon: 73.741, duration_min: 120, price: 0, per: 'person', day: 4, notes: 'Crowded, keep Dadi near the entrance', source: 'sample', status: 'proposed' },
  { id: 'pl-5', name: 'Dudhsagar Falls jeep trip', area: 'Mollem', category: 'nature', lat: 15.3144, lon: 74.3143, duration_min: 300, price: 1200, per: 'person', day: null, notes: 'Bumpy jeep ride, not step-free', source: 'sample', status: 'proposed' },
  { id: 'pl-6', name: 'Shri Mangueshi Temple', area: 'Ponda', category: 'temple', lat: 15.451, lon: 73.9806, duration_min: 45, price: 0, per: 'person', day: 2, notes: 'Step-free path to the main hall', source: 'sample', status: 'selected' },
  { id: 'pl-7', name: 'Sunset cruise on the Mandovi', area: 'Panaji', category: 'activity', lat: 15.4989, lon: 73.8278, duration_min: 90, price: 600, per: 'person', day: 3, notes: 'Live music, snacks on board (no peanuts)', source: 'live', status: 'selected' },
]

export const RESTAURANTS: Restaurant[] = [
  { id: 'r-1', name: 'Vinayak Family Restaurant', cuisine: 'Goan', area: 'Assagao', meal: 'lunch', day: 2, date: '2026-12-27', time: '13:00', price_for_two: 900, veg_only: false, lat: 15.592, lon: 73.764, notes: 'Has a vegetarian thali, no peanuts in the fish curry', source: 'sample', status: 'selected' },
  { id: 'r-2', name: 'Gunpowder', cuisine: 'South Indian and Kerala', area: 'Assagao', meal: 'dinner', day: 1, date: '2026-12-26', time: '20:00', price_for_two: 1800, veg_only: false, lat: 15.5934, lon: 73.7619, notes: 'Plenty of vegetarian dishes', source: 'sample', status: 'selected' },
  { id: 'r-3', name: 'Sagar Pure Veg', cuisine: 'North Indian', area: 'Panaji', meal: 'lunch', day: 3, date: '2026-12-28', time: '13:30', price_for_two: 700, veg_only: true, lat: 15.4989, lon: 73.83, notes: 'Pure veg, suits Dadi', source: 'sample', status: 'selected' },
  { id: 'r-4', name: "Britto's", cuisine: 'Seafood', area: 'Baga', meal: 'dinner', day: 3, date: '2026-12-28', time: '20:00', price_for_two: 1600, veg_only: false, lat: 15.556, lon: 73.751, notes: 'Beachfront, step-free seating', source: 'sample', status: 'selected' },
  { id: 'r-5', name: 'Ritz Classic', cuisine: 'Goan thali', area: 'Panaji', meal: 'lunch', day: 4, date: '2026-12-29', time: '13:00', price_for_two: 1000, veg_only: false, lat: 15.4986, lon: 73.8312, notes: 'Veg thali on request', source: 'sample', status: 'selected' },
  { id: 'r-6', name: 'Infantaria Cafe', cuisine: 'Bakery and breakfast', area: 'Calangute', meal: 'breakfast', day: 2, date: '2026-12-27', time: '09:00', price_for_two: 600, veg_only: false, lat: 15.544, lon: 73.762, notes: 'Step-free entrance', source: 'live', status: 'selected' },
  { id: 'r-7', name: 'Thalassa', cuisine: 'Greek', area: 'Vagator', meal: 'dinner', day: null, date: null, time: null, price_for_two: 2200, veg_only: false, lat: 15.6, lon: 73.7396, notes: 'Cliff-top view, lots of steps', source: 'sample', status: 'proposed' },
]

/** The day-by-day timeline, built from the flights, hotel, places and meals above so each entry carries its own cost. */
export function buildItinerary(n: number): ItineraryItem[] {
  const out: Omit<ItineraryItem, 'id'>[] = []
  const date = (day: number) => `2026-12-${26 + day - 1}`
  const add = (day: number, time: string, kind: ItineraryItem['kind'], title: string, place: string, lat: number, lon: number, ref: string | null, cost: number | null, notes = '') =>
    out.push({ day, date: date(day), time, title, place, lat, lon, notes, kind, ref, cost })
  const place = (day: number, time: string, id: string) => {
    const x = PLACES.find((p) => p.id === id)!
    add(day, time, 'place', x.name, x.area, x.lat, x.lon, id, x.price * n, x.notes)
  }
  const meal = (id: string) => {
    const r = RESTAURANTS.find((x) => x.id === id)!
    add(r.day!, r.time!, 'food', `${r.meal[0].toUpperCase()}${r.meal.slice(1)} at ${r.name}`, r.area, r.lat, r.lon, id, Math.round((r.price_for_two * n) / 2), r.notes)
  }
  add(1, '07:10', 'travel', 'Fly Bengaluru to Goa (IndiGo 6E-512)', 'Dabolim Airport', 15.3808, 73.8314, 'f-1', 4200 * n)
  add(1, '10:00', 'stay', 'Check in at Coconut Grove Resort', 'Candolim', 15.5183, 73.762, 'h-1', 6500)
  place(1, '17:30', 'pl-3')
  meal('r-2')
  add(2, '08:00', 'stay', 'Night at Coconut Grove Resort', 'Candolim', 15.5183, 73.762, 'h-1', 6500)
  meal('r-6')
  place(2, '10:30', 'pl-1')
  meal('r-1')
  place(2, '16:00', 'pl-6')
  add(3, '08:00', 'stay', 'Night at Coconut Grove Resort', 'Candolim', 15.5183, 73.762, 'h-1', 6500)
  place(3, '10:00', 'pl-2')
  meal('r-3')
  place(3, '17:00', 'pl-7')
  meal('r-4')
  add(4, '08:00', 'stay', 'Night at Coconut Grove Resort', 'Candolim', 15.5183, 73.762, 'h-1', 6500)
  place(4, '10:00', 'pl-4')
  meal('r-5')
  add(4, '16:30', 'other', 'Free time at the pool', 'Candolim', 15.5183, 73.762, null, null)
  add(5, '10:00', 'stay', 'Pack and check out', 'Candolim', 15.5183, 73.762, 'h-1', null)
  add(5, '17:15', 'travel', 'Fly home to Bengaluru', 'Dabolim Airport', 15.3808, 73.8314, null, null)
  return out.sort((a, b) => a.day - b.day || a.time.localeCompare(b.time)).map((x, i) => ({ ...x, id: `i-${i + 1}` }))
}
