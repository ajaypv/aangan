import { ExternalLink, Plane } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Flight, Room } from '@/types'
import { dayLabel, durationLabel, money, plural } from '../format'
import { BoardCard, EmptyLine, FlashItem, SourceChip, StatusChip } from './shared'

function FlightRow({ f, travellers, currency }: { f: Flight; travellers: number; currency: string }) {
  const duration = durationLabel(f.dep, f.arr)
  const total = f.per === 'person' ? f.price * travellers : f.price
  const showTotal = f.per === 'person' && travellers > 1
  return (
    <FlashItem id={f.id} className={cn('space-y-3 px-4 py-3.5', f.status === 'rejected' && 'opacity-60')}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
        <p className="min-w-0 font-semibold">
          {f.airline} <span className="num font-normal text-ink-2">{f.number}</span>
        </p>
        <span className="flex flex-wrap items-center gap-1.5">
          <SourceChip source={f.source} />
          <StatusChip status={f.status} />
        </span>
      </div>

      {/* 07:10 ------ 1h 20m ------ 08:30, with the airports and the stops under it */}
      <div className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-3 gap-y-0.5">
        <p className="num text-xl font-bold leading-none">{f.dep}</p>
        <div className="flex items-center gap-2" aria-hidden="true">
          <span className="h-px flex-1 bg-edge" />
          <Plane className="size-4 shrink-0 text-ink-2" />
          <span className="h-px flex-1 bg-edge" />
        </div>
        <p className="num text-xl font-bold leading-none">{f.arr}</p>
        <p className="t-caption num">{f.from}</p>
        <p className="t-caption text-center">
          {duration && <span className="num">{duration}</span>}
          {duration && ' · '}
          {f.stops === 0 ? 'Nonstop' : plural(f.stops, 'stop')}
        </p>
        <p className="t-caption num text-right">{f.to}</p>
      </div>

      <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-2">
        <div>
          <p className="num text-lg font-bold leading-tight">
            {money(f.price, currency)} <span className="t-secondary font-normal">{f.per === 'person' ? 'per person' : 'total'}</span>
          </p>
          {showTotal && (
            <p className="t-secondary num">
              {money(total, currency)} for {plural(travellers, 'traveller')}
            </p>
          )}
          <p className="t-caption mt-0.5">{dayLabel(f.date)}</p>
        </div>
        {f.link && (
          <a
            href={f.link}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex min-h-11 items-center gap-1.5 rounded-md px-2 text-sm font-semibold text-brand-text hover:bg-hover lg:min-h-9"
          >
            View on airline site
            <ExternalLink className="size-4" aria-hidden="true" />
            <span className="sr-only">(opens in a new tab)</span>
          </a>
        )}
      </div>
    </FlashItem>
  )
}

export function FlightsCard({ room }: { room: Room }) {
  const flights = room.plan.flights
  const travellers = Math.max(1, room.plan.travelers.length)
  const currency = room.plan.budget?.currency ?? 'INR'
  return (
    <BoardCard id="flights" section="flights" title="Flights" icon={<Plane className="size-4" />} count={flights.length}>
      {flights.length === 0 ? (
        <EmptyLine>Ask Aangan to look for flights once you know the dates.</EmptyLine>
      ) : (
        <ul className="divide-y divide-line" aria-label="Flight options">
          {flights.map((f) => (
            <FlightRow key={f.id} f={f} travellers={travellers} currency={currency} />
          ))}
        </ul>
      )}
    </BoardCard>
  )
}
