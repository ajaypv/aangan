import { categoryOf } from '@/lib/money'
import { cn } from '@/lib/utils'

/** A category's icon in a soft circle. Decorative: the category name always appears in text next to it. */
export function CategoryIcon({ id, size = 40 }: { id: string; size?: number }) {
  const Icon = categoryOf(id).icon
  return (
    <span aria-hidden="true" className="grid shrink-0 place-items-center rounded-full bg-surface-2 text-ink-2" style={{ width: size, height: size }}>
      <Icon style={{ width: size * 0.5, height: size * 0.5 }} />
    </span>
  )
}

/** A horizontal bar with an optional budget tick. Purely visual: the numbers are in text beside it. */
export function Bar({ pct, tickPct, tone = 'brand', className }: { pct: number; tickPct?: number | null; tone?: 'brand' | 'warning' | 'danger'; className?: string }) {
  const fill = tone === 'danger' ? 'bg-[var(--rw-danger)]' : tone === 'warning' ? 'bg-[var(--rw-warning)]' : 'bg-brand'
  return (
    <div aria-hidden="true" className={cn('relative h-2.5 w-full rounded-full bg-surface-3', className)}>
      <div className={cn('h-full rounded-full transition-[width] duration-300', fill)} style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
      {tickPct != null && tickPct >= 0 && tickPct <= 100 && (
        <span className="absolute -top-1 h-[1.125rem] w-0.5 rounded-full bg-ink" style={{ left: `calc(${tickPct}% - 1px)` }} />
      )}
    </div>
  )
}
