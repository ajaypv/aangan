import { categoryOf, formatINR, type CategoryTotal } from '@/lib/money'
import { cn } from '@/lib/utils'
import { Card, CardBody, CardHeader } from '@/ui/primitives'
import { Bar, CategoryIcon } from './parts'

/** Where the money went, biggest first. A tick on a bar marks that category's monthly budget. */
export function CategoryBars({ cats, budgets, showBudgets }: { cats: CategoryTotal[]; budgets: Record<string, number | null>; showBudgets: boolean }) {
  const budgetOf = (id: string) => (showBudgets ? budgets[id] || null : null)
  const scale = Math.max(1, ...cats.map((c) => c.amount), ...cats.map((c) => budgetOf(c.id) ?? 0))

  return (
    <Card as="section" aria-label="Spending by category">
      <CardHeader title="Where it went" subtitle={showBudgets ? 'A tick marks the monthly budget' : undefined} />
      <CardBody>
        {cats.length === 0 ? (
          <p className="t-secondary py-2">Nothing spent in this period.</p>
        ) : (
          <ul className="space-y-4">
            {cats.map((c) => {
              const info = categoryOf(c.id)
              const budget = budgetOf(c.id)
              const over = budget !== null && c.amount > budget
              return (
                <li key={c.id} className="flex items-start gap-3" aria-label={`${info.label}: ${formatINR(c.amount)}, ${c.share}% of spending${budget ? `, budget ${formatINR(budget)}${over ? `, ${formatINR(c.amount - budget)} over` : ''}` : ''}`}>
                  <CategoryIcon id={c.id} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="truncate font-semibold">{info.label}</span>
                      <span className="num font-semibold">{formatINR(c.amount)}</span>
                    </div>
                    <Bar className="mt-2" pct={(c.amount / scale) * 100} tickPct={budget ? (budget / scale) * 100 : null} tone={over ? 'danger' : 'brand'} />
                    <div className="mt-1.5 flex justify-between gap-3">
                      <span className="t-caption">{c.share}% of spending</span>
                      {budget && (
                        <span className={cn('t-caption num', over && 'font-semibold text-[var(--rw-text-danger)]')}>
                          {over ? `${formatINR(c.amount - budget)} over budget` : `Budget ${formatINR(budget)}`}
                        </span>
                      )}
                    </div>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </CardBody>
    </Card>
  )
}
