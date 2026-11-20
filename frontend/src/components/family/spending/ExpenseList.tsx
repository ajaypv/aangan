import { Trash2 } from 'lucide-react'
import { useState } from 'react'
import { memberOf } from '@/lib/format'
import { categoryOf, formatINR, groupByDay, type Expense } from '@/lib/money'
import type { Snapshot } from '@/types'
import { Button, IconButton, MemberDots } from '@/ui/primitives'
import { CategoryIcon } from './parts'

const PAGE = 20

/** Recent spending grouped by day. Each entry has a delete button; the view offers an undo afterwards. */
export function ExpenseList({ snap, rows, deleting, onDelete }: { snap: Snapshot; rows: Expense[]; deleting: string | null; onDelete: (e: Expense) => void }) {
  const [shown, setShown] = useState(PAGE)
  const groups = groupByDay(rows, snap.now.date)
  let budget = shown
  const pageGroups = groups
    .map((g) => {
      const items = g.items.slice(0, Math.max(0, budget))
      budget -= items.length
      return { ...g, items }
    })
    .filter((g) => g.items.length > 0)

  if (rows.length === 0) return <p className="t-secondary rounded-xl border border-dashed border-edge px-4 py-6">No expenses in this period.</p>

  return (
    <div>
      <div className="space-y-5">
        {pageGroups.map((g) => (
          <section key={g.date} aria-label={g.heading}>
            <div className="mb-1.5 flex items-baseline justify-between px-1">
              <h4 className="text-sm font-bold">{g.heading}</h4>
              <span className="num t-caption">{formatINR(g.total)}</span>
            </div>
            <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface shadow-xs">
              {g.items.map((e) => {
                const member = memberOf(snap, e.member_id)
                const info = categoryOf(e.category)
                return (
                  <li key={e.id} className="flex min-h-16 items-center gap-3 px-3 py-2">
                    <CategoryIcon id={e.category} size={38} />
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-semibold">{e.note || info.label}</p>
                      <p className="t-secondary flex items-center gap-1.5 truncate">
                        {member && <MemberDots members={[member]} />}
                        <span className="truncate">
                          {member?.name ?? e.member_id}
                          {e.note ? ` · ${info.label}` : ''}
                        </span>
                      </p>
                    </div>
                    <span className="num shrink-0 font-semibold">{formatINR(e.amount)}</span>
                    <IconButton label={`Delete ${e.note || info.label}, ${formatINR(e.amount)}`} disabled={deleting === e.id} onClick={() => onDelete(e)}>
                      <Trash2 className="size-4" aria-hidden="true" />
                    </IconButton>
                  </li>
                )
              })}
            </ul>
          </section>
        ))}
      </div>
      {rows.length > shown && (
        <div className="mt-4 flex justify-center">
          <Button variant="secondary" onClick={() => setShown((n) => n + PAGE)}>
            Show more ({rows.length - shown} more)
          </Button>
        </div>
      )}
    </div>
  )
}
