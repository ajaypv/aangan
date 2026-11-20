import { memberOf } from '@/lib/format'
import { budgetState, byMember, formatINR, type Expense, type Period } from '@/lib/money'
import { cn } from '@/lib/utils'
import type { Snapshot } from '@/types'
import { Avatar, Button, Card, Pill } from '@/ui/primitives'
import { Bar } from './parts'

const HEADING: Record<Period, string> = { month: 'Spent this month', last_month: 'Spent last month', all: 'Spent so far' }
const VERSUS: Record<Period, string> = { month: 'last month', last_month: 'the month before', all: '' }

interface Props {
  snap: Snapshot
  period: Period
  rows: Expense[]
  total: number
  change: { previous: number; changePct: number } | null
  budgetTotal: number | null
  onSetBudget: () => void
}

/** The total for the chosen period, how it compares, and progress against the monthly budget. */
export function SummaryCard({ snap, period, rows, total, change, budgetTotal, onSetBudget }: Props) {
  const people = byMember(rows)
  const budget = budgetTotal ? budgetState(total, budgetTotal) : null
  const showBudget = period !== 'all'

  return (
    <Card as="section" aria-label="Spending summary" className="p-4 lg:p-5">
      <p className="t-secondary">{HEADING[period]}</p>
      <p className="num mt-1 text-3xl font-extrabold leading-none">{formatINR(total)}</p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <span className="t-secondary">
          {rows.length} {rows.length === 1 ? 'expense' : 'expenses'}
        </span>
        {change && (
          <Pill tone={change.changePct > 0 ? 'warning' : change.changePct < 0 ? 'success' : 'neutral'}>
            {change.changePct === 0 ? `Same as ${VERSUS[period]}` : `${change.changePct > 0 ? 'Up' : 'Down'} ${Math.abs(change.changePct)}% on ${VERSUS[period]}`}
          </Pill>
        )}
      </div>

      {showBudget && (
        <div className="mt-4 border-t border-line pt-4">
          {budget && budgetTotal ? (
            <div>
              <div className="flex items-baseline justify-between gap-3">
                <span className="text-sm font-semibold">Monthly budget</span>
                <span className={cn('num text-sm font-semibold', budget.tone === 'over' ? 'text-[var(--rw-text-danger)]' : budget.tone === 'warning' ? 'text-[var(--rw-text-warning)]' : 'text-ink-2')}>
                  {budget.tone === 'over' ? `${formatINR(-budget.left)} over ${formatINR(budgetTotal)}` : `${formatINR(budget.left)} left of ${formatINR(budgetTotal)}`}
                </span>
              </div>
              <div
                role="progressbar"
                aria-label="Share of the monthly budget spent"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={Math.min(100, Math.round(budget.pct))}
                aria-valuetext={`${Math.round(budget.pct)}% of the budget spent`}
                className="mt-2"
              >
                <Bar pct={budget.pct} tone={budget.tone === 'over' ? 'danger' : budget.tone === 'warning' ? 'warning' : 'brand'} />
              </div>
              <p className="t-caption mt-1.5">{Math.round(budget.pct)}% of the budget spent</p>
            </div>
          ) : (
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="t-secondary">No monthly budget yet.</p>
              <Button variant="tertiary" size="sm" onClick={onSetBudget}>
                Set a monthly budget
              </Button>
            </div>
          )}
        </div>
      )}

      {people.length >= 2 && (
        <div className="mt-4 border-t border-line pt-4">
          <p className="mb-2 text-sm font-semibold">By person</p>
          <ul className="flex flex-wrap gap-2">
            {people.map((p) => {
              const m = memberOf(snap, p.id)
              return (
                <li key={p.id} className="inline-flex items-center gap-1.5 rounded-full bg-surface-2 py-1 pl-1 pr-3 text-sm">
                  {m ? <Avatar member={m} size={22} /> : null}
                  <span className="font-semibold">{m?.name ?? p.id}</span>
                  <span className="num text-ink-2">{formatINR(p.amount)}</span>
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </Card>
  )
}
