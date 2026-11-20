import { BadgeCheck, CheckCircle2, Circle, CircleHelp, ClipboardList, Gavel, Info, Receipt, Ticket } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Room } from '@/types'
import { Pill } from '@/ui/primitives'
import { joinList, money, nameFor } from '../format'
import { CATEGORY_LABEL } from './CostStrip'
import { BoardCard, EmptyLine, FlashItem } from './shared'

/** The cost lines behind the summary strip: what Aangan added by hand (transport, extras), each marked as an estimate until confirmed. */
export function CostsCard({ room }: { room: Room }) {
  const { costs, cost_summary: sum } = room.plan
  return (
    <BoardCard id="costs" section="costs" title="Extra costs" icon={<Receipt className="size-4" />} count={costs.length}>
      {costs.length === 0 ? (
        <EmptyLine>Costs add up here as the plan fills in.</EmptyLine>
      ) : (
        <>
          <ul className="divide-y divide-line" aria-label="Cost lines">
            {costs.map((c) => (
              <FlashItem key={c.label} id={`cost:${c.label}`} className="flex items-center gap-3 px-4 py-2.5">
                <div className="min-w-0 flex-1">
                  <p className="font-semibold leading-snug">{c.label}</p>
                  <p className="t-caption">{CATEGORY_LABEL[(c.category ?? 'other') as keyof typeof CATEGORY_LABEL] ?? 'Other'}</p>
                </div>
                {c.status === 'estimate' ? <Pill tone="warning">Estimate</Pill> : <Pill tone="success">Confirmed</Pill>}
                <p className="num w-24 shrink-0 text-right font-semibold">{money(c.amount, sum.currency)}</p>
              </FlashItem>
            ))}
          </ul>
          <p className="t-secondary border-t border-line px-4 py-3">Flights, stay, meals and places are counted from what you have selected, in the summary above.</p>
        </>
      )}
    </BoardCard>
  )
}

export function DecisionsCard({ room }: { room: Room }) {
  const ds = room.plan.decisions
  return (
    <BoardCard id="decisions" section="decisions" title="Decisions" icon={<Gavel className="size-4" />} count={ds.length}>
      {ds.length === 0 ? (
        <EmptyLine>Decisions you agree on will be kept here.</EmptyLine>
      ) : (
        <ul className="divide-y divide-line" aria-label="Decisions">
          {ds.map((d) => (
            <FlashItem key={d.id} id={d.id} className="flex items-start gap-3 px-4 py-3">
              <BadgeCheck className="mt-0.5 size-5 shrink-0 text-[var(--rw-text-success)]" aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <p className="font-semibold leading-snug">{d.text}</p>
                <p className="t-caption">
                  {d.by.length > 0 && <>Agreed by {joinList(d.by.map((id) => nameFor(room, id)))}. </>}
                  <span className="num">{d.ts}</span>
                </p>
              </div>
            </FlashItem>
          ))}
        </ul>
      )}
    </BoardCard>
  )
}

export function QuestionsCard({ room }: { room: Room }) {
  const qs = [...room.plan.open_questions].sort((a, b) => Number(a.resolved) - Number(b.resolved))
  const open = qs.filter((q) => !q.resolved).length
  return (
    <BoardCard id="questions" section="questions" title="Open questions" icon={<CircleHelp className="size-4" />} count={open}>
      {qs.length === 0 ? (
        <EmptyLine>Questions Aangan still needs answered will appear here.</EmptyLine>
      ) : (
        <ul className="divide-y divide-line" aria-label="Open questions">
          {qs.map((q) => (
            <FlashItem key={q.id} id={q.id} className={cn('flex items-start gap-3 px-4 py-3', q.resolved && 'opacity-70')}>
              <Info className="mt-0.5 size-5 shrink-0 text-info" aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <p className={cn('font-semibold leading-snug', q.resolved && 'line-through')}>{q.text}</p>
                <p className="t-caption">
                  Asked by {nameFor(room, q.asked_by)}, <span className="num">{q.ts}</span>
                </p>
              </div>
              {q.resolved && <Pill tone="success">Resolved</Pill>}
            </FlashItem>
          ))}
        </ul>
      )}
    </BoardCard>
  )
}

/** Read only: the contract has no endpoint for ticking items, so nothing here pretends to be a control. */
export function ChecklistCard({ room }: { room: Room }) {
  const cs = room.plan.checklist
  const done = cs.filter((c) => c.done).length
  return (
    <BoardCard id="checklist" section="checklist" title="Before you go" icon={<ClipboardList className="size-4" />} count={cs.length - done}>
      {cs.length === 0 ? (
        <EmptyLine>Things to do before you go will be listed here.</EmptyLine>
      ) : (
        <ul className="divide-y divide-line" aria-label="Checklist">
          {cs.map((c) => (
            <FlashItem key={c.id} id={c.id} className="flex items-start gap-3 px-4 py-3">
              {c.done ? (
                <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-[var(--rw-text-success)]" aria-label="Done" role="img" />
              ) : (
                <Circle className="mt-0.5 size-5 shrink-0 text-ink-2" aria-label="Not done yet" role="img" />
              )}
              <div className="min-w-0 flex-1">
                <p className={cn('leading-snug', c.done && 'text-ink-2 line-through')}>{c.text}</p>
                {c.owner && <p className="t-caption">{nameFor(room, c.owner)}</p>}
              </div>
            </FlashItem>
          ))}
        </ul>
      )}
    </BoardCard>
  )
}

export function BookingsCard({ room }: { room: Room }) {
  const bs = room.bookings
  const currency = room.plan.cost_summary.currency
  return (
    <BoardCard id="bookings" section="bookings" title="Bookings" icon={<Ticket className="size-4" />} count={bs.length}>
      {bs.length === 0 ? (
        <EmptyLine>Nothing booked yet. Bookings here are demo bookings: no real money moves.</EmptyLine>
      ) : (
        <ul className="divide-y divide-line" aria-label="Bookings">
          {bs.map((b) => (
            <FlashItem key={b.id} id={b.id} className="space-y-1 px-4 py-3">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                {b.demo && <Pill tone="info">Demo booking</Pill>}
                <p className="num rounded bg-surface-2 px-1.5 py-0.5 font-mono text-sm font-semibold">{b.ref}</p>
              </div>
              <p className="font-semibold leading-snug">{b.title}</p>
              <p className="t-caption num">
                {money(b.amount, currency)} · {b.ts}
              </p>
            </FlashItem>
          ))}
        </ul>
      )}
    </BoardCard>
  )
}
