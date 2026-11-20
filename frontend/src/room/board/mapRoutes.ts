import type { ItineraryItem } from '@/types'

export interface DayRoute {
  day: number
  points: [number, number][]
}

/** Schematic connections in visit order, not road directions. Each day is independent. */
export function itineraryRoutes(items: readonly Pick<ItineraryItem, 'day' | 'time' | 'lat' | 'lon'>[]): DayRoute[] {
  const days = new Map<number, [number, number][]>()
  for (const item of [...items].sort((a, b) => a.day - b.day || a.time.localeCompare(b.time))) {
    if (!Number.isFinite(item.lat) || !Number.isFinite(item.lon) || Math.abs(item.lat) > 90 || Math.abs(item.lon) > 180) continue
    const points = days.get(item.day) ?? []
    const previous = points.at(-1)
    if (!previous || previous[0] !== item.lat || previous[1] !== item.lon) points.push([item.lat, item.lon])
    days.set(item.day, points)
  }
  return [...days].filter(([, points]) => points.length > 1).map(([day, points]) => ({ day, points }))
}
