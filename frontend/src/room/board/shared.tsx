import { AlertTriangle, Check } from 'lucide-react'
import type { ElementType, ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { Card, Pill } from '@/ui/primitives'
import type { PlanItemStatus, PlanSource } from '@/types'
import { money } from '../format'
import { useItemFlash, useSectionFlash, type SectionKey } from '../useBoardFlash'

/** One card of the plan board: icon, title, an optional count and action, and a glow while its content just changed. */
export function BoardCard({
  id,
  section,
  title,
  icon,
  count,
  action,
  children,
  className,
}: {
  id: string
  section: SectionKey
  title: string
  icon: ReactNode
  count?: number
  action?: ReactNode
  children: ReactNode
  className?: string
}) {
  const flash = useSectionFlash(section)
  return (
    <Card as="section" aria-labelledby={`board-${id}`} data-board={id} className={cn('overflow-hidden', flash && 'room-flash', className)}>
      <div className="flex items-center gap-3 px-4 pb-1 pt-4">
        <span className="grid size-8 shrink-0 place-items-center rounded-full bg-brand-soft text-brand-text" aria-hidden="true">
          {icon}
        </span>
        <h3 id={`board-${id}`} className="t-card min-w-0 flex-1 truncate">
          {title}
        </h3>
        {count !== undefined && count > 0 && <Pill className="num">{count}</Pill>}
        {action}
      </div>
      {children}
    </Card>
  )
}

/** A calm one-line prompt for a card with nothing in it yet. */
export const EmptyLine = ({ children }: { children: ReactNode }) => <p className="t-secondary px-4 pb-4 pt-2">{children}</p>

/** A row or small card that lights up when this item is new or changed. */
export function FlashItem({ id, as, className, children }: { id: string; as?: ElementType; className?: string; children: ReactNode }) {
  const flash = useItemFlash(id)
  const Tag: ElementType = as ?? 'li'
  return <Tag className={cn(className, flash && 'room-flash-row')}>{children}</Tag>
}

export const SourceChip = ({ source }: { source: PlanSource }) =>
  source === 'live' ? (
    <Pill tone="success">
      <span className="size-1.5 rounded-full bg-[var(--rw-success)]" aria-hidden="true" />
      Live<span className="sr-only"> (a real search result)</span>
    </Pill>
  ) : (
    <Pill>Sample<span className="sr-only"> (built-in sample data, not a real offer)</span></Pill>
  )

export function StatusChip({ status }: { status: PlanItemStatus }) {
  switch (status) {
    case 'selected':
      return <Pill tone="brand">Selected</Pill>
    case 'booked':
      return (
        <Pill tone="success">
          <Check className="size-3" aria-hidden="true" />
          Booked
        </Pill>
      )
    case 'rejected':
      return <Pill tone="danger">Rejected</Pill>
    default:
      return <Pill>Proposed</Pill>
  }
}

/** Costs against the budget. Over budget is its own clear state: red bar, warning icon and the amount over in words. */
export function BudgetMeter({ spent, budget, currency, className, showTotal = true }: { spent: number; budget: number | null; currency: string; className?: string; showTotal?: boolean }) {
  if (budget === null || budget <= 0) {
    return (
      <div className={className}>
        <p className="num text-lg font-bold">{money(spent, currency)}</p>
        <p className="t-secondary">Estimated so far. No budget set yet: tell Aangan what you would like to spend.</p>
      </div>
    )
  }
  const ratio = spent / budget
  const over = spent > budget
  const near = !over && ratio >= 0.85
  return (
    <div className={className} data-over-budget={over || undefined}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        {showTotal ? (
          <p className="num text-lg font-bold">
            {money(spent, currency)} <span className="t-secondary font-normal">of {money(budget, currency)}</span>
          </p>
        ) : (
          <p className="t-secondary num">Budget {money(budget, currency)}</p>
        )}
        {over ? (
          <p className="inline-flex items-center gap-1.5 text-sm font-semibold text-[var(--rw-text-danger)]">
            <AlertTriangle className="size-4" aria-hidden="true" />
            Over budget by {money(spent - budget, currency)}
          </p>
        ) : (
          <p className={cn('num text-sm font-semibold', near ? 'text-[var(--rw-text-warning)]' : 'text-[var(--rw-text-success)]')}>{money(budget - spent, currency)} left</p>
        )}
      </div>
      <div
        role="progressbar"
        aria-label="Costs against budget"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.min(100, Math.round(ratio * 100))}
        aria-valuetext={over ? `Over budget by ${money(spent - budget, currency)}` : `${Math.round(ratio * 100)} percent of the budget`}
        className="mt-2 h-2.5 overflow-hidden rounded-full bg-surface-2"
      >
        <div
          className={cn('h-full rounded-full transition-[width] duration-500', over ? 'bg-[var(--rw-danger)]' : near ? 'bg-[var(--rw-warning)]' : 'bg-brand')}
          style={{ width: `${Math.min(100, ratio * 100)}%` }}
        />
      </div>
    </div>
  )
}
