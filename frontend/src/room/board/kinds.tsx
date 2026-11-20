import { Bed, Church, CircleDot, Footprints, Landmark, MapPin, Plane, Soup, Store, Ticket, Trees, Utensils, Waves, type LucideIcon } from 'lucide-react'
import type { ItineraryItem } from '@/types'

/** Icons and colours used by the itinerary, the place cards and the map legend, so one kind looks the same everywhere. */
export const KIND: Record<NonNullable<ItineraryItem['kind']> | 'other', { label: string; icon: LucideIcon; tone: string }> = {
  travel: { label: 'Travel', icon: Plane, tone: 'bg-info-bg text-info' },
  stay: { label: 'Stay', icon: Bed, tone: 'bg-brand-soft text-brand-text' },
  place: { label: 'Place', icon: MapPin, tone: 'bg-success-bg text-[var(--rw-text-success)]' },
  food: { label: 'Meal', icon: Utensils, tone: 'bg-warning-bg text-[var(--rw-text-warning)]' },
  other: { label: 'Other', icon: CircleDot, tone: 'bg-surface-2 text-ink-2' },
}

export const kindOf = (k: ItineraryItem['kind'] | undefined) => KIND[k ?? 'other'] ?? KIND.other

export const CATEGORY_ICON: Record<string, { label: string; icon: LucideIcon }> = {
  sight: { label: 'Sight', icon: Landmark },
  beach: { label: 'Beach', icon: Waves },
  market: { label: 'Market', icon: Store },
  temple: { label: 'Temple', icon: Church },
  nature: { label: 'Nature', icon: Trees },
  activity: { label: 'Activity', icon: Ticket },
  food_walk: { label: 'Food walk', icon: Soup },
  other: { label: 'Place', icon: Footprints },
}

export const categoryOf = (c: string) => CATEGORY_ICON[c] ?? CATEGORY_ICON.other

export const MEAL_LABEL: Record<string, string> = { breakfast: 'Breakfast', lunch: 'Lunch', dinner: 'Dinner', snack: 'Snack' }

export const durationText = (min: number | null | undefined) => {
  if (!min) return ''
  const h = Math.floor(min / 60)
  const m = min % 60
  return h ? (m ? `${h} h ${m} min` : `${h} h`) : `${m} min`
}
