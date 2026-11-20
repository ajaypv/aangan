import { cn } from '@/lib/utils'
import type { CostCategory, CostSummary, Room } from '@/types'
import { Pill } from '@/ui/primitives'
import { money, plural } from '../format'
import { BudgetMeter } from './shared'

export const CATEGORY_LABEL: Record<CostCategory, string> = {
  flights: 'Flights',
  transport: 'Train, bus & car',
  stay: 'Stay',
  food: 'Food',
  activities: 'Activities',
  local: 'Local travel',
  other: 'Other',
}
const ORDER: CostCategory[] = ['flights', 'transport', 'stay', 'food', 'activities', 'local', 'other']

/**
 * The cost summary at the top of the plan: total and per person in large type, a bar against the budget (calm under it, a clear
 * "over by" when over), and small bars for where the money goes. All numbers come from `plan.cost_summary`.
 */
export function CostStrip({ room }: { room: Room }) {
  const wide = useMediaQuery('(min-width: 1024px)')
  const [expanded, setExpanded] = useState(false)
  const c: CostSummary = room.plan.cost_summary
  const booked = room.bookings.reduce((s, b) => s + b.amount, 0)
  // Only the rows with money in them: a "Flights ₹0" line on a trip by train is noise. With nothing priced yet, keep the main four so the card has shape.
  const priced = ORDER.filter((k) => (c.by_category[k] ?? 0) > 0)
  const rows = (priced.length ? priced : (['flights', 'stay', 'food', 'activities'] as CostCategory[])).map((k) => ({ key: k, amount: c.by_category[k] ?? 0 }))
  const biggest = Math.max(1, ...rows.map((r) => r.amount))
  const allBooked = c.total > 0 && booked >= c.total

  return (
    <div
      className={cn('room-budget rounded-lg border p-3.5', c.over_budget ? 'border-[var(--rw-danger)] bg-danger-bg' : 'border-line bg-surface-3')}
      role="group"
      aria-label="Cost summary"
      data-cost-strip
    >
      <div className="room-budget-head">
        <div className="room-budget-totals grid grid-cols-2 gap-4">
          <div className="min-w-0">
            <p className="t-caption font-semibold uppercase tracking-wide">Total</p>
            <p className="num text-2xl font-extrabold leading-tight sm:text-3xl" data-cost-total>
              {money(c.total, c.currency)}
            </p>
          </div>
          <div className="min-w-0">
            <p className="t-caption font-semibold uppercase tracking-wide">Per person</p>
            <p className="num text-2xl font-extrabold leading-tight sm:text-3xl">{money(c.per_person, c.currency)}</p>
            <p className="t-caption">{plural(c.travellers, 'traveller')}</p>
          </div>
        </div>

        <div className="room-budget-meter mt-3">
          {c.budget !== null && c.budget > 0 ? (
            <BudgetMeter spent={c.total} budget={c.budget} currency={c.currency} showTotal={false} />
          ) : (
            <p className="t-caption">No budget set yet. Tell Aangan your limit.</p>
          )}
        </div>

        <button type="button" className="room-budget-toggle" aria-expanded={expanded} aria-controls="room-budget-details" onClick={() => setExpanded((open) => !open)}>
          Breakdown <ChevronDown className={cn('size-3.5', expanded && 'rotate-180')} aria-hidden="true" />
        </button>
      </div>

      <div className="room-budget-note mt-3 flex items-center gap-2">
        {allBooked ? <Pill tone="success">Booked (demo)</Pill> : <Pill tone="warning">Estimate</Pill>}
        <p className="t-caption">{allBooked ? 'Everything in the plan has a demo booking.' : 'Updates with your choices.'}</p>
      </div>

      <ul id="room-budget-details" className={cn('mt-3 grid gap-x-6 gap-y-2.5 sm:grid-cols-2', wide && !expanded && 'hidden')} aria-label="Where the money goes">
        {rows.map((r) => (
          <li key={r.key}>
            <div className="flex items-baseline justify-between gap-2 text-sm">
              <span>{CATEGORY_LABEL[r.key]}</span>
              <span className="num font-semibold">{money(r.amount, c.currency)}</span>
            </div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-2" aria-hidden="true">
              <div className="h-full rounded-full bg-brand" style={{ width: `${(r.amount / biggest) * 100}%` }} />
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
import { ChevronDown } from 'lucide-react'
import { useState } from 'react'
import { useMediaQuery } from '@/lib/useMediaQuery'
