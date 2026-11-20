import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import type { Room } from '@/types'

/**
 * Which board cards (and which items inside them) changed since the last snapshot, so they can glow for a moment. The first snapshot
 * flashes nothing. Sections are compared by content; items by their id (costs by label), so a new or edited item lights up on its own.
 */
export type SectionKey =
  | 'summary'
  | 'approval'
  | 'flights'
  | 'transport'
  | 'hotels'
  | 'map'
  | 'itinerary'
  | 'places'
  | 'restaurants'
  | 'costs'
  | 'decisions'
  | 'questions'
  | 'checklist'
  | 'bookings'

const FLASH_MS = 2600

const slices = (r: Room): Record<SectionKey, unknown> => {
  const p = r.plan
  return {
    summary: [p.goal, p.destination, p.origin, p.dates, p.travelers, p.budget, p.preferences],
    approval: r.pending_approval,
    flights: p.flights,
    transport: p.transport,
    hotels: p.hotels,
    map: [
      p.destination, p.origin,
      p.hotels.map((h) => [h.lat, h.lon, h.status]),
      p.places.map((i) => [i.lat, i.lon, i.status]),
      p.restaurants.map((i) => [i.lat, i.lon, i.status]),
      p.itinerary.map((i) => [i.day, i.time, i.lat, i.lon]),
    ],
    itinerary: p.itinerary,
    places: p.places,
    restaurants: p.restaurants,
    costs: [p.costs, p.cost_summary],
    decisions: p.decisions,
    questions: p.open_questions,
    checklist: p.checklist,
    bookings: r.bookings,
  }
}

const itemsOf = (r: Room): Map<string, string> => {
  const m = new Map<string, string>()
  const add = (id: string, v: unknown) => m.set(id, JSON.stringify(v))
  const p = r.plan
  p.flights.forEach((x) => add(x.id, x))
  p.transport.forEach((x) => add(x.id, x))
  p.hotels.forEach((x) => add(x.id, x))
  p.itinerary.forEach((x) => add(x.id, x))
  p.places.forEach((x) => add(x.id, x))
  p.restaurants.forEach((x) => add(x.id, x))
  p.decisions.forEach((x) => add(x.id, x))
  p.open_questions.forEach((x) => add(x.id, x))
  p.checklist.forEach((x) => add(x.id, x))
  p.costs.forEach((x) => add(`cost:${x.label}`, x))
  r.bookings.forEach((x) => add(x.id, x))
  return m
}

interface Flash {
  sections: ReadonlySet<string>
  items: ReadonlySet<string>
}

const Ctx = createContext<Flash>({ sections: new Set(), items: new Set() })

export function useFlash() {
  return useContext(Ctx)
}

/** True while this section just changed. */
export const useSectionFlash = (key: SectionKey) => useFlash().sections.has(key)
/** True while this item just appeared or changed. */
export const useItemFlash = (id: string) => useFlash().items.has(id)

export function BoardFlashProvider({ room, onPlanChanged, children }: { room: Room; onPlanChanged?: () => void; children: ReactNode }) {
  const prev = useRef<{ s: Record<SectionKey, string>; i: Map<string, string> } | null>(null)
  const [sections, setSections] = useState<ReadonlySet<string>>(new Set())
  const [items, setItems] = useState<ReadonlySet<string>>(new Set())
  const timers = useRef(new Map<string, number>())
  const changed = useRef(onPlanChanged)
  changed.current = onPlanChanged

  useEffect(() => {
    const now = slices(room)
    const s = Object.fromEntries(Object.entries(now).map(([k, v]) => [k, JSON.stringify(v)])) as Record<SectionKey, string>
    const i = itemsOf(room)
    const before = prev.current
    prev.current = { s, i }
    if (!before) return

    const secs = (Object.keys(s) as SectionKey[]).filter((k) => s[k] !== before.s[k])
    const its = [...i.keys()].filter((id) => before.i.get(id) !== i.get(id))
    if (secs.length === 0) return
    changed.current?.()

    setSections((cur) => new Set([...cur, ...secs]))
    setItems((cur) => new Set([...cur, ...its]))
    for (const k of [...secs, ...its]) {
      window.clearTimeout(timers.current.get(k))
      timers.current.set(
        k,
        window.setTimeout(() => {
          timers.current.delete(k)
          setSections((cur) => {
            if (!cur.has(k)) return cur
            const n = new Set(cur)
            n.delete(k)
            return n
          })
          setItems((cur) => {
            if (!cur.has(k)) return cur
            const n = new Set(cur)
            n.delete(k)
            return n
          })
        }, FLASH_MS),
      )
    }
  }, [room])

  useEffect(() => {
    const t = timers.current
    return () => t.forEach((id) => window.clearTimeout(id))
  }, [])

  const value = useMemo(() => ({ sections, items }), [sections, items])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
