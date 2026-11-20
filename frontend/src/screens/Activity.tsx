import { CheckCircle2, MessageSquare, Sparkles, XCircle } from 'lucide-react'
import { useMemo, useState } from 'react'
import { EventLine } from '@/components/ask/EventLine'
import { describeEvent, groupByDay, type Described } from '@/lib/describe'
import { joinNames } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useApp } from '@/state/AppState'
import type { Snapshot, ToolEvent } from '@/types'
import { AgentBadge, Card, EmptyState, Pill, SegmentedControl, Switch } from '@/ui/primitives'

const hhmm = (ts: string) => ts.slice(0, 5)

/** One thing Aangan did: the sentence, who did it, when, and (folded away) the raw call for anyone who wants to check. */
function Row({ d, event }: { d: Described; event: ToolEvent }) {
  return (
    <li className="px-4 py-2.5">
      <div className="flex items-start gap-2">
        <ul className="min-w-0 flex-1" aria-label="Action">
          <EventLine d={d} className="py-0" />
        </ul>
        <div className="flex shrink-0 flex-col items-end gap-1 pt-0.5">
          <AgentBadge agent={d.agent} />
          <time className="num t-caption">{hhmm(d.ts)}</time>
        </div>
      </div>
      <details className="mt-1.5 pl-7 text-xs text-ink-2">
        <summary className="min-h-7 cursor-pointer font-semibold">Details</summary>
        <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-surface-3 p-2 font-mono">
          {JSON.stringify({ tool: event.tool, stage: event.stage, args: event.args, result: event.result, ms: event.ms }, null, 2)}
        </pre>
      </details>
    </li>
  )
}

function Timeline({ snap }: { snap: Snapshot }) {
  const [lookups, setLookups] = useState(false)
  const { all, groups, hiddenCount } = useMemo(() => {
    const byId = new Map(snap.events.map((e) => [e.id, e]))
    // "Recalled N things" lines belong under a reply in Ask; the timeline lists only actions, and lookups on request.
    const described = snap.events.map((e) => describeEvent(e, snap)).filter((d) => d.kind === 'action' || d.kind === 'lookup')
    const shown = described.filter((d) => lookups || d.kind === 'action')
    const days = groupByDay(shown)
      .map((g) => ({ label: g.label, items: [...g.items].reverse() }))
      .reverse()
    return { all: byId, groups: days, hiddenCount: described.length - described.filter((d) => d.kind === 'action').length }
  }, [snap, lookups])

  if (snap.events.filter((e) => e.agent !== 'orchestrator').length === 0) {
    return (
      <EmptyState icon={<Sparkles className="size-6" aria-hidden="true" />} title="Nothing yet">
        Ask Aangan to book, remind or plan something. Everything it does is listed here, in plain words.
      </EmptyState>
    )
  }

  return (
    <div className="space-y-6">
      {hiddenCount > 0 && (
        <div className="flex items-center justify-between gap-3">
          <p className="t-secondary">{lookups ? 'Showing what Aangan looked up too' : `${hiddenCount} lookups and checks are hidden`}</p>
          <Switch checked={lookups} onChange={setLookups} label="Show lookups" />
        </div>
      )}
      {groups.length === 0 ? (
        <EmptyState icon={<Sparkles className="size-6" aria-hidden="true" />} title="No actions yet">
          Aangan has only looked things up so far. Turn on lookups to see them.
        </EmptyState>
      ) : (
        groups.map((g) => (
          <section key={g.label} aria-label={g.label}>
            <h2 className="t-card mb-2">{g.label}</h2>
            <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface shadow-xs">
              {g.items.map((d) => (
                <Row key={d.id} d={d} event={all.get(d.id)!} />
              ))}
            </ul>
          </section>
        ))
      )}
    </div>
  )
}

function Messages({ snap, me }: { snap: Snapshot; me: string | null }) {
  const notes = [...snap.notifications].reverse()
  if (notes.length === 0) {
    return (
      <EmptyState icon={<MessageSquare className="size-6" aria-hidden="true" />} title="No family messages yet">
        When Aangan books something or something needs attention, the right people are told here.
      </EmptyState>
    )
  }
  return (
    <ul className="space-y-3">
      {notes.map((n) => {
        const forYou = me !== null && n.to.includes(me)
        return (
          <li key={n.id}>
            <Card className={cn('space-y-2 p-4', forYou && 'border-[var(--selected-edge)]')}>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="font-semibold">To {n.to.length === snap.members.length && n.to.length > 1 ? 'everyone' : joinNames(snap, n.to)}</span>
                <Pill tone="brand">{n.kind}</Pill>
                <AgentBadge agent={n.agent} />
                {forYou && <Pill tone="success">For you</Pill>}
                <span className="num ml-auto text-ink-2">
                  {n.date} {n.at}
                </span>
              </div>
              <p className="rounded-lg bg-surface-3 px-3 py-2 text-[15px] leading-snug">{n.text}</p>
              <p className="flex items-center gap-1.5 text-xs text-ink-2">
                {n.status === 'sent' && (
                  <>
                    <CheckCircle2 className="size-3.5 text-[var(--rw-text-success)]" aria-hidden="true" /> Delivered over Agora Chat
                  </>
                )}
                {n.status === 'in_app' && 'Shown in the app only. Agora Chat is not connected yet.'}
                {n.status === 'failed' && (
                  <span className="flex items-center gap-1.5 font-semibold text-[var(--rw-text-danger)]">
                    <XCircle className="size-3.5" aria-hidden="true" /> Agora Chat delivery failed
                  </span>
                )}
              </p>
            </Card>
          </li>
        )
      })}
    </ul>
  )
}

/** "What Aangan did": every action in plain sentences, grouped by day, plus the messages sent to the family. */
export function ActivityScreen() {
  const { snap, personaId } = useApp()
  const [view, setView] = useState<'actions' | 'messages'>('actions')
  if (!snap) return null
  return (
    <div className="mx-auto max-w-3xl p-4 pb-10">
      <SegmentedControl
        label="What Aangan did"
        className="mb-4"
        value={view}
        onChange={setView}
        options={[
          { value: 'actions', label: 'Actions' },
          { value: 'messages', label: `Family messages${snap.notifications.length ? ` (${snap.notifications.length})` : ''}` },
        ]}
      />
      {view === 'actions' ? <Timeline snap={snap} /> : <Messages snap={snap} me={personaId} />}
    </div>
  )
}
