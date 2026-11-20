import { Accessibility, Hotel as HotelIcon, MapPin, Star } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Room } from '@/types'
import { Pill } from '@/ui/primitives'
import { money, nights, plural } from '../format'
import { BoardCard, EmptyLine, FlashItem, SourceChip, StatusChip } from './shared'

export function HotelsCard({ room }: { room: Room }) {
  const hotels = room.plan.hotels
  const dates = room.plan.dates
  const n = dates ? nights(dates.start, dates.end) : null
  const currency = room.plan.budget?.currency ?? 'INR'
  return (
    <BoardCard id="hotels" section="hotels" title="Hotels" icon={<HotelIcon className="size-4" />} count={hotels.length}>
      {hotels.length === 0 ? (
        <EmptyLine>Hotels show up here after Aangan searches for places to stay.</EmptyLine>
      ) : (
        <ul className="divide-y divide-line" aria-label="Hotel options">
          {hotels.map((h) => (
            <FlashItem key={h.id} id={h.id} className={cn('space-y-2 px-4 py-3.5', h.status === 'rejected' && 'opacity-60')}>
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
                <p className="min-w-0 font-semibold">{h.name}</p>
                <span className="flex flex-wrap items-center gap-1.5">
                  <SourceChip source={h.source} />
                  <StatusChip status={h.status} />
                </span>
              </div>
              <p className="t-secondary flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="inline-flex items-center gap-1">
                  <MapPin className="size-3.5" aria-hidden="true" />
                  {h.area}
                </span>
                <span className="num inline-flex items-center gap-1">
                  <Star className="size-3.5 fill-[var(--rw-warning)] text-[var(--rw-warning)]" aria-hidden="true" />
                  <span className="sr-only">Rated </span>
                  {h.rating.toFixed(1)}
                </span>
                {h.step_free && (
                  <Pill tone="success">
                    <Accessibility className="size-3" aria-hidden="true" />
                    Step-free
                  </Pill>
                )}
              </p>
              <p className="num text-lg font-bold leading-tight">
                {money(h.price_per_night, currency)} <span className="t-secondary font-normal">per night</span>
              </p>
              {n !== null && (
                <p className="t-secondary num">
                  {money(h.price_per_night * n, currency)} for {plural(n, 'night')}
                </p>
              )}
            </FlashItem>
          ))}
        </ul>
      )}
    </BoardCard>
  )
}
