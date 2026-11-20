import { Clock, Leaf, Utensils } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Room } from '@/types'
import { Pill } from '@/ui/primitives'
import { money } from '../format'
import { MEAL_LABEL } from './kinds'
import { BoardCard, EmptyLine, FlashItem, SourceChip, StatusChip } from './shared'

export function RestaurantsCard({ room }: { room: Room }) {
  const rs = room.plan.restaurants
  const currency = room.plan.cost_summary.currency
  return (
    <BoardCard id="restaurants" section="restaurants" title="Where to eat" icon={<Utensils className="size-4" />} count={rs.length}>
      {rs.length === 0 ? (
        <EmptyLine>Aangan will suggest places to eat that suit everyone's food needs.</EmptyLine>
      ) : (
        <ul className="grid gap-px bg-line sm:grid-cols-2 sm:[&>li:last-child:nth-child(odd)]:col-span-2" aria-label="Restaurants">
          {rs.map((r) => (
            <FlashItem key={r.id} id={r.id} className={cn('space-y-1.5 bg-surface px-4 py-3.5', r.status === 'rejected' && 'opacity-60')}>
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <p className="min-w-0 font-semibold leading-snug">{r.name}</p>
                {r.veg_only && (
                  <Pill tone="success">
                    <Leaf className="size-3" aria-hidden="true" />
                    Pure veg
                  </Pill>
                )}
              </div>
              <p className="t-secondary">
                {r.cuisine} <span aria-hidden="true">·</span> {r.area}
              </p>
              <p className="t-secondary num flex flex-wrap items-center gap-x-3 gap-y-1">
                <Pill tone="warning">{MEAL_LABEL[r.meal] ?? r.meal}</Pill>
                {r.day && r.time ? (
                  <span className="inline-flex items-center gap-1">
                    <Clock className="size-3.5" aria-hidden="true" />
                    Day {r.day}, {r.time}
                  </span>
                ) : (
                  <span>Not scheduled yet</span>
                )}
                <span className="font-semibold text-ink">{money(r.price_for_two, currency)} for two</span>
              </p>
              {r.notes && <p className="t-caption">{r.notes}</p>}
              <div className="flex flex-wrap items-center gap-1.5">
                <SourceChip source={r.source} />
                {r.status === 'proposed' ? <Pill>Proposed</Pill> : <StatusChip status={r.status} />}
              </div>
            </FlashItem>
          ))}
        </ul>
      )}
    </BoardCard>
  )
}
