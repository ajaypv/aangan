import { Brain, Check, Search, X } from 'lucide-react'
import type { Described } from '@/lib/describe'
import { cn } from '@/lib/utils'
import { AgentBadge } from '@/ui/primitives'

/** One sentence about one thing Aangan did, with a small status mark. Failures say what went wrong in plain words. */
export function EventLine({ d, showAgent = false, className }: { d: Described; showAgent?: boolean; className?: string }) {
  const failed = !d.ok
  const Icon = failed ? X : d.kind === 'context' ? Brain : d.kind === 'lookup' ? Search : Check
  const tone = failed
    ? 'bg-danger-bg text-[var(--rw-text-danger)]'
    : d.kind === 'action'
      ? 'bg-success-bg text-[var(--rw-text-success)]'
      : 'bg-surface-2 text-ink-2'
  return (
    <li className={cn('flex items-start gap-2.5 py-1.5', className)}>
      <span className={cn('mt-0.5 grid size-5 shrink-0 place-items-center rounded-full', tone)} aria-hidden="true">
        <Icon className="size-3" />
      </span>
      <span className="min-w-0 flex-1 text-sm leading-snug">
        {failed && <span className="sr-only">Did not work: </span>}
        <span className={cn(d.kind === 'action' ? 'font-semibold' : 'text-ink-2')}>{d.text}</span>
        {failed && d.reason && <span className="block text-[var(--rw-text-danger)]">{d.reason}</span>}
      </span>
      {showAgent && <AgentBadge agent={d.agent} className="shrink-0" />}
    </li>
  )
}
