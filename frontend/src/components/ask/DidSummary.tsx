import { ChevronDown } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { summarize } from '@/lib/describe'
import { cn } from '@/lib/utils'
import type { Snapshot, ToolEvent } from '@/types'
import { EventLine } from './EventLine'

/** "Aangan did 3 things": one quiet line under a reply that opens into short sentences, never raw tool names. */
export function DidSummary({ events, snap }: { events: ToolEvent[]; snap: Snapshot }) {
  const [open, setOpen] = useState(false)
  const s = useMemo(() => summarize(events, snap), [events, snap])
  if (!s.line) return null
  const trouble = s.failed.length > 0
  return (
    <Collapsible open={open} onOpenChange={setOpen} className="pl-1">
      <CollapsibleTrigger
        className={cn(
          '-ml-2 inline-flex min-h-9 items-center gap-1.5 rounded-md px-2 text-sm font-semibold transition-colors hover:bg-hover',
          trouble && s.actions.every((d) => !d.ok) ? 'text-[var(--rw-text-danger)]' : 'text-brand-text',
        )}
      >
        {s.line}
        <ChevronDown className={cn('size-4 transition-transform', open && 'rotate-180')} aria-hidden="true" />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ul className="mt-1 divide-y divide-line rounded-lg border border-line bg-surface px-3" aria-label="What Aangan did for this reply">
          {[...s.context, ...s.actions, ...s.lookups].map((d) => (
            <EventLine key={d.id} d={d} />
          ))}
        </ul>
      </CollapsibleContent>
    </Collapsible>
  )
}
