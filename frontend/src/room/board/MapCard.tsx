import { Map as MapIcon, Maximize2, Minimize2 } from 'lucide-react'
import { lazy, Suspense, useState } from 'react'
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import type { Room } from '@/types'
import { Button, Skeleton } from '@/ui/primitives'
import { PIN } from './mapPins'
import { BoardCard, EmptyLine } from './shared'

// Leaflet is only fetched when a map is about to show, so the main bundle stays small.
const MapView = lazy(() => import('./MapView'))

function MapLegend() {
  return (
    <ul className="room-map-legend mt-2 flex flex-wrap gap-x-3 gap-y-2" aria-label="Map key">
      {Object.entries(PIN).map(([kind, pin]) => (
        <li key={kind} className="t-caption inline-flex items-center gap-1.5">
          <span className="room-map-legend-icon" style={{ background: pin.color }} aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={pin.path} /></svg>
          </span>
          {pin.label}
        </li>
      ))}
    </ul>
  )
}

export function MapCard({ room, className, day = null }: { room: Room; className?: string; day?: number | null }) {
  const [expanded, setExpanded] = useState(false)
  const p = room.plan
  const hasPoints = Boolean(p.origin || p.destination || p.hotels.length || p.places.length || p.restaurants.length || p.itinerary.length)
  const routeLabel = day === null ? "Lines connect each day's planned stops" : `Day ${day}: planned stop order`

  return (
    <Dialog open={expanded} onOpenChange={setExpanded}>
      <BoardCard
        id="map" section="map" title="Trip map" icon={<MapIcon className="size-4" />} className={className}
        action={
          <DialogTrigger asChild>
            <Button variant="secondary" size="sm" disabled={!hasPoints} aria-label="Expand map" icon={<Maximize2 className="size-3.5" aria-hidden="true" />}>Expand</Button>
          </DialogTrigger>
        }
      >
        {!hasPoints ? (
          <EmptyLine>Places appear on the map as the plan takes shape.</EmptyLine>
        ) : (
          <div className="px-4 pb-4 pt-2">
            <div className="room-map isolate overflow-hidden rounded-lg border border-line">
              <Suspense fallback={<Skeleton className="room-map-surface" />}>
                <MapView plan={p} day={day} className="room-map-surface w-full" />
              </Suspense>
            </div>
            <MapLegend />
            {p.itinerary.length > 1 && (
              <p className="t-caption mt-2"><span className="room-route-key" aria-hidden="true" />{routeLabel}, not driving directions.</p>
            )}
          </div>
        )}
      </BoardCard>
      <DialogContent className="room-map-dialog" showCloseButton={false}>
        <div className="flex shrink-0 items-start justify-between gap-3">
          <div className="min-w-0">
            <DialogTitle>Expanded trip map</DialogTitle>
            <DialogDescription className="mt-1">
              {p.destination?.name ?? room.title} / {day === null ? 'All days' : `Day ${day}`}. Select a marker for details.
            </DialogDescription>
          </div>
          <DialogClose asChild>
            <Button variant="secondary" size="sm" aria-label="Close expanded map" icon={<Minimize2 className="size-4" aria-hidden="true" />}>Close</Button>
          </DialogClose>
        </div>
        {hasPoints ? (
          <div className="room-map room-map-expanded isolate min-h-0 flex-1 overflow-hidden rounded-lg border border-line">
            <Suspense fallback={<Skeleton className="h-full w-full" />}>
              <MapView plan={p} day={day} expanded className="h-full w-full" />
            </Suspense>
          </div>
        ) : (
          <div className="grid flex-1 place-items-center"><p className="t-secondary">Places appear here as the plan takes shape.</p></div>
        )}
        <div className="shrink-0">
          <MapLegend />
          {p.itinerary.length > 1 && <p className="t-caption mt-2"><span className="room-route-key" aria-hidden="true" />{routeLabel}, not driving directions.</p>}
        </div>
      </DialogContent>
    </Dialog>
  )
}
