import { Map as MapIcon } from 'lucide-react'
import { lazy, Suspense } from 'react'
import { cn } from '@/lib/utils'
import type { Room } from '@/types'
import { Skeleton } from '@/ui/primitives'
import { BoardCard, EmptyLine } from './shared'

// Leaflet is only fetched when a map is about to show, so the main bundle stays small.
const MapView = lazy(() => import('./MapView'))

const LEGEND: { label: string; swatch: string; shape: string }[] = [
  { label: 'Destination', swatch: '#227e9e', shape: 'rounded-full' },
  { label: 'Starting point', swatch: '#6f6964', shape: 'rounded-full' },
  { label: 'Stay', swatch: '#8a4f9e', shape: 'rounded-[3px]' },
  { label: 'Places', swatch: '#3a8a3e', shape: 'rounded-full' },
  { label: 'Meals', swatch: '#c46a12', shape: 'rotate-45 rounded-[2px]' },
]

export function MapCard({ room, className }: { room: Room; className?: string }) {
  const p = room.plan
  const hasPoints = Boolean(p.origin || p.destination || p.hotels.length || p.places.length || p.restaurants.length || p.itinerary.length)
  return (
    <BoardCard id="map" section="map" title="Map" icon={<MapIcon className="size-4" />} className={className}>
      {!hasPoints ? (
        <EmptyLine>Places appear on the map as the plan takes shape.</EmptyLine>
      ) : (
        <div className="px-4 pb-4 pt-2">
          <div className="room-map isolate overflow-hidden rounded-lg border border-line">
            <Suspense fallback={<Skeleton className="h-72 xl:h-[min(560px,calc(100dvh-14rem))]" />}>
              <MapView plan={p} className={cn('h-72 w-full xl:h-[min(560px,calc(100dvh-14rem))]')} />
            </Suspense>
          </div>
          <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1" aria-label="Map key">
            {LEGEND.map((l) => (
              <li key={l.label} className="t-caption inline-flex items-center gap-1.5">
                <span className={cn('inline-block size-2.5', l.shape)} style={{ background: l.swatch }} aria-hidden="true" />
                {l.label}
              </li>
            ))}
          </ul>
        </div>
      )}
    </BoardCard>
  )
}
