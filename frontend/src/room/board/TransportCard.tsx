import { Bus, Car, CarTaxiFront, Route, TrainFront, type LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Room, TransportMode, TransportOption } from '@/types'
import { dayLabel, minutesLabel, money, plural } from '../format'
import { BoardCard, EmptyLine, FlashItem, SourceChip, StatusChip } from './shared'

const MODE: Record<TransportMode, { label: string; icon: LucideIcon }> = {
  train: { label: 'Train', icon: TrainFront },
  bus: { label: 'Bus', icon: Bus },
  car: { label: 'Own car', icon: Car },
  cab: { label: 'Cab', icon: CarTaxiFront },
}

const SEATS_PER_CAR = 4

const LOCAL_LABEL = { cab: 'Cabs and autos', public: 'Public transport: metro, buses and autos', own_car: 'Your own car: fuel and parking' } as const

function Row({ t, travellers, currency }: { t: TransportOption; travellers: number; currency: string }) {
  const mode = MODE[t.mode] ?? { label: t.mode, icon: Route }
  const Icon = mode.icon
  const vehicles = Math.max(1, Math.ceil(travellers / SEATS_PER_CAR))
  const perPerson = t.per === 'person'
  const total = perPerson ? t.price * travellers : t.price * vehicles
  return (
    <FlashItem id={t.id} className={cn('space-y-2 px-4 py-3.5', t.status === 'rejected' && 'opacity-60')}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
        <span className="grid size-8 shrink-0 place-items-center rounded-full bg-info-bg text-info" aria-hidden="true">
          <Icon className="size-4" />
        </span>
        <p className="min-w-0 font-semibold">
          {mode.label} <span className="font-normal text-ink-2">{t.label}</span>
        </p>
        <span className="flex flex-wrap items-center gap-1.5">
          <SourceChip source={t.source} />
          <StatusChip status={t.status} />
        </span>
      </div>
      <p className="t-secondary">
        <span className="num">{t.from}</span> to <span className="num">{t.to}</span> · about <span className="num">{minutesLabel(t.duration_min)}</span> ·{' '}
        <span className="num">{t.distance_km} km</span>
      </p>
      <div>
        <p className="num text-lg font-bold leading-tight">
          {money(t.price, currency)} <span className="t-secondary font-normal">{perPerson ? 'per person' : 'per car'}</span>
        </p>
        <p className="t-secondary num">
          {money(total, currency)} for {perPerson ? plural(travellers, 'traveller') : plural(vehicles, 'car')}
        </p>
        <p className="t-caption mt-0.5">{dayLabel(t.date)}</p>
      </div>
    </FlashItem>
  )
}

/**
 * Getting there by train, bus or car instead of flying (all estimates from the distance), and how the group gets around once there.
 * Shown only when there is something to show: a plan that flies does not need an empty card.
 */
export function TransportCard({ room }: { room: Room }) {
  const options = room.plan.transport
  const local = room.plan.local_mode
  if (options.length === 0 && !local) return null
  const travellers = Math.max(1, room.plan.cost_summary?.travellers ?? room.plan.travelers.length)
  const currency = room.plan.budget?.currency ?? 'INR'
  return (
    <BoardCard id="transport" section="transport" title="Train, bus & car" icon={<TrainFront className="size-4" />} count={options.length}>
      {options.length === 0 ? (
        <EmptyLine>Ask Aangan for a train, bus or car instead of flying.</EmptyLine>
      ) : (
        <>
          <p className="t-caption px-4 pb-1">
            Estimates from the distance between the cities, not timetables or live fares. Choosing one replaces the flight for that journey. Book trains on IRCTC.
          </p>
          <ul className="divide-y divide-line" aria-label="Train, bus and car options">
            {options.map((t) => (
              <Row key={t.id} t={t} travellers={travellers} currency={currency} />
            ))}
          </ul>
        </>
      )}
      {local && (
        <p className="t-secondary border-t border-line px-4 py-3">
          Getting around there: <span className="font-semibold text-ink">{LOCAL_LABEL[local]}</span>
        </p>
      )}
    </BoardCard>
  )
}
