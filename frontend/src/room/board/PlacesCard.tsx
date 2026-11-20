import { Accessibility, Clock, MapPinned } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Room } from '@/types'
import { Pill } from '@/ui/primitives'
import { money } from '../format'
import { categoryOf, durationText } from './kinds'
import { BoardCard, EmptyLine, FlashItem, SourceChip } from './shared'
import { StatusChip } from './shared'

export function PlacesCard({ room }: { room: Room }) {
  const places = room.plan.places
  const currency = room.plan.cost_summary.currency
  return (
    <BoardCard id="places" section="places" title="Places to visit" icon={<MapPinned className="size-4" />} count={places.length}>
      {places.length === 0 ? (
        <EmptyLine>Tell Aangan what you like (beaches, temples, markets) and places to visit will appear here.</EmptyLine>
      ) : (
        <ul className="grid gap-px bg-line sm:grid-cols-2 sm:[&>li:last-child:nth-child(odd)]:col-span-2" aria-label="Places to visit">
          {places.map((p) => {
            const cat = categoryOf(p.category)
            const Icon = cat.icon
            const free = !p.price
            return (
              <FlashItem key={p.id} id={p.id} className={cn('space-y-1.5 bg-surface px-4 py-3.5', p.status === 'rejected' && 'opacity-60')}>
                <div className="flex items-start gap-3">
                  <span className="grid size-9 shrink-0 place-items-center rounded-full bg-success-bg text-[var(--rw-text-success)]" aria-hidden="true">
                    <Icon className="size-[18px]" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold leading-snug">{p.name}</p>
                    <p className="t-secondary">
                      {p.area} <span aria-hidden="true">·</span> <span className="sr-only">Category: </span>
                      {cat.label}
                    </p>
                  </div>
                </div>
                <p className="t-secondary num flex flex-wrap items-center gap-x-3 gap-y-1">
                  {p.duration_min ? (
                    <span className="inline-flex items-center gap-1">
                      <Clock className="size-3.5" aria-hidden="true" />
                      {durationText(p.duration_min)}
                    </span>
                  ) : null}
                  <span className={cn('font-semibold', free ? 'text-[var(--rw-text-success)]' : 'text-ink')}>{free ? 'Free' : `${money(p.price, currency)} per person`}</span>
                  {p.day ? <span>Day {p.day}</span> : <span>Not scheduled yet</span>}
                </p>
                {p.notes && (
                  <p className="t-caption flex items-start gap-1.5">
                    {/step-free/i.test(p.notes) && !/(not|no) step-free/i.test(p.notes) && <Accessibility className="mt-px size-3.5 shrink-0 text-[var(--rw-text-success)]" aria-hidden="true" />}
                    {p.notes}
                  </p>
                )}
                <div className="flex flex-wrap items-center gap-1.5">
                  <SourceChip source={p.source} />
                  {p.status !== 'proposed' ? <StatusChip status={p.status} /> : <Pill>Proposed</Pill>}
                </div>
              </FlashItem>
            )
          })}
        </ul>
      )}
    </BoardCard>
  )
}
