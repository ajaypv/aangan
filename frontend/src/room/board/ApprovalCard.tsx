import { Check, Info, ShieldCheck, X } from 'lucide-react'
import { useState } from 'react'
import { cn } from '@/lib/utils'
import type { Participant, Room } from '@/types'
import { Button, Card, Pill } from '@/ui/primitives'
import { money, participantById } from '../format'
import { useSectionFlash } from '../useBoardFlash'

/**
 * A booking waits for a human tap. The price is the biggest thing on the card. Approve and Decline are for the person the approval needs
 * ("host" means only the host); everyone else sees why they are off and who can. Nothing here moves real money, and it says so.
 */
export function ApprovalCard({ room, me, onDecide }: { room: Room; me: Participant | undefined; onDecide: (approve: boolean) => Promise<string | null> }) {
  const a = room.pending_approval
  const flash = useSectionFlash('approval')
  const [busy, setBusy] = useState<'approve' | 'decline' | null>(null)
  const [error, setError] = useState<string | null>(null)
  if (!a || a.status !== 'waiting') return null

  const host = participantById(room, room.host_participant_id)
  const allowed = Boolean(me) && (a.needs === 'anyone' || me?.id === room.host_participant_id)
  const alreadyApproved = Boolean(me && a.approvals.includes(me.id))
  const included = a.items
    .map((id) => room.plan.flights.find((f) => f.id === id)?.number ?? room.plan.hotels.find((h) => h.id === id)?.name)
    .filter(Boolean)
  const currency = room.plan.budget?.currency ?? 'INR'
  const why = !allowed ? `Only ${host?.name ?? 'the host'} can approve this.` : alreadyApproved ? 'You already approved this. Waiting for the others.' : ''

  const decide = async (yes: boolean) => {
    setBusy(yes ? 'approve' : 'decline')
    setError(null)
    const problem = await onDecide(yes)
    setBusy(null)
    if (problem) setError(problem)
  }

  return (
    <Card
      as="section"
      aria-labelledby="board-approval"
      data-board="approval"
      className={cn('room-pop overflow-hidden border-[var(--selected-edge)] bg-brand-soft', flash && 'room-flash')}
    >
      <div className="flex items-center gap-2 px-4 pt-4">
        <ShieldCheck className="size-5 shrink-0 text-brand-text" aria-hidden="true" />
        <h3 id="board-approval" className="t-card flex-1">
          Waiting for approval
        </h3>
        <Pill tone="warning">Needs {a.needs === 'host' ? 'the host' : 'one of you'}</Pill>
      </div>
      <div className="room-approval-body space-y-3 px-4 pb-4 pt-2">
        <div className="room-approval-details">
          <p className="font-semibold">{a.title}</p>
          <p className="num mt-1 text-3xl font-extrabold leading-none">{money(a.amount, currency)}</p>
          {included.length > 0 && <p className="t-secondary mt-1.5">Includes {included.join(', ')}</p>}
          <p className="t-secondary mt-1.5">{a.summary}</p>
        </div>
        <p className="room-approval-demo inline-flex items-start gap-1.5 rounded-md bg-surface px-2.5 py-1.5 text-sm font-medium">
          <Info className="mt-0.5 size-4 shrink-0 text-info" aria-hidden="true" />
          Demo booking: no real money moves.
        </p>
        <div className="room-approval-actions flex flex-wrap gap-2">
          <Button
            icon={<Check className="size-4" aria-hidden="true" />}
            disabled={!allowed || alreadyApproved || busy !== null}
            loading={busy === 'approve'}
            aria-describedby={why ? 'approval-why' : undefined}
            onClick={() => void decide(true)}
            className="flex-1 sm:flex-none"
          >
            Approve
          </Button>
          <Button
            variant="secondary"
            icon={<X className="size-4" aria-hidden="true" />}
            disabled={!allowed || busy !== null}
            loading={busy === 'decline'}
            aria-describedby={why ? 'approval-why' : undefined}
            onClick={() => void decide(false)}
            className="flex-1 sm:flex-none"
          >
            Decline
          </Button>
        </div>
        {why && (
          <p id="approval-why" className="t-secondary">
            {why}
          </p>
        )}
        {error && (
          <p role="alert" className="room-approval-error text-sm font-medium text-[var(--rw-text-danger)]">
            {error}
          </p>
        )}
      </div>
    </Card>
  )
}
