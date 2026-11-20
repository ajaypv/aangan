import { AlertTriangle, BookOpen, CalendarClock, Check, Info, Lightbulb, MessageCircleQuestion, Mic, Pill as PillIcon, School, Send, Sparkles, Wallet } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { describeEvent } from '@/lib/describe'
import { dosesToday, kidOf, schoolToday, seniorOf } from '@/lib/domain'
import { addDays, dayLabel, joinNames, memberOf, minutes, suggestionsFor } from '@/lib/format'
import { cn } from '@/lib/utils'
import { PlanTogetherCard } from '@/room/PlanTogetherCard'
import { useApp } from '@/state/AppState'
import type { CalendarEvent, Snapshot } from '@/types'
import {
  AgentBadge,
  Button,
  Card,
  EmptyState,
  IconButton,
  ListCard,
  ListRow,
  Pill,
  Skeleton,
  SectionHeader,
  inputClass,
} from '@/ui/primitives'
import { useImpact, type Impact, type ImpactResult, type Money } from '@/ui/useImpact'

/* ---------------------------------------------------------------------------------------------------------------------------------
 * Needs your attention: real items from the family's state, most urgent first. Home shows only the top three.
 * ------------------------------------------------------------------------------------------------------------------------------ */

type Severity = 'danger' | 'warning' | 'info'
interface AttentionItem {
  key: string
  severity: Severity
  icon: ReactNode
  title: string
  detail?: string
  action?: { label: string; run: () => void }
}

const SEVERITY_ORDER: Record<Severity, number> = { danger: 0, warning: 1, info: 2 }
const ICON_TONE: Record<Severity, string> = {
  danger: 'bg-danger-bg text-[var(--rw-text-danger)]',
  warning: 'bg-warning-bg text-[var(--rw-text-warning)]',
  info: 'bg-info-bg text-info',
}
const TOP_ITEMS = 3

/** Events that overlap for at least one shared family member, today and the next two days. */
function clashes(snap: Snapshot) {
  const found: { key: string; date: string; a: CalendarEvent; b: CalendarEvent; who: string[] }[] = []
  for (let i = 0; i < 3; i++) {
    const date = addDays(snap.now.date, i)
    const day = snap.calendar.filter((e) => e.date === date).sort((x, y) => x.start.localeCompare(y.start))
    for (let p = 0; p < day.length; p++) {
      for (let q = p + 1; q < day.length; q++) {
        const [a, b] = [day[p], day[q]]
        const shared = a.member_ids.filter((id) => b.member_ids.includes(id))
        if (shared.length && minutes(a.start) < minutes(b.end) && minutes(b.start) < minutes(a.end)) found.push({ key: `${a.id}-${b.id}`, date, a, b, who: shared })
      }
    }
  }
  return found
}

function buildAttention(
  snap: Snapshot,
  go: { ask: () => void; schedule: () => void; did: () => void; refill: (memberId: string, med: string) => void },
): AttentionItem[] {
  const items: AttentionItem[] = []
  const icon = 'size-5'

  if (snap.pending) {
    items.push({
      key: 'pending',
      severity: 'info',
      icon: <MessageCircleQuestion className={icon} />,
      title: 'Aangan is waiting for your answer',
      detail: typeof snap.pending.agent === 'string' ? `A proposal from the ${snap.pending.agent} agent needs a yes or a no.` : undefined,
      action: { label: 'Answer', run: go.ask },
    })
  }

  for (const m of snap.members) {
    const senior = seniorOf(snap, m.id)
    if (senior) {
      for (const med of senior.meds.filter((x) => x.stock_days <= 3)) {
        items.push({
          key: `stock-${m.id}-${med.id}`,
          severity: med.stock_days <= 2 ? 'danger' : 'warning',
          icon: <PillIcon className={icon} />,
          title: `${m.name}: ${med.name} has ${med.stock_days} ${med.stock_days === 1 ? 'day' : 'days'} left`,
          detail: 'Order a refill so it does not run out.',
          action: { label: 'Reorder', run: () => go.refill(m.id, med.name) },
        })
      }
      const missed = dosesToday(snap, senior).filter((d) => d.status === 'missed')
      if (missed.length) {
        items.push({
          key: `missed-${m.id}`,
          severity: 'danger',
          icon: <AlertTriangle className={icon} />,
          title: `${m.name} missed ${missed.length} ${missed.length === 1 ? 'dose' : 'doses'} today`,
          detail: missed.map((d) => `${d.med} at ${d.slot}`).join(', '),
          action: { label: 'What happened', run: go.did },
        })
      }
    }

    const kid = kidOf(snap, m.id)
    if (kid) {
      const school = schoolToday(snap, m.id)
      const start = school?.start
      const now = minutes(snap.now.time)
      if (kid.status !== 'at_school' && school && now > minutes(school.start) && now < minutes(school.end)) {
        items.push({
          key: `late-${m.id}`,
          severity: 'warning',
          icon: <School className={icon} />,
          title: `${m.name} has not reached school yet`,
          detail: `School started at ${start}.`,
          action: { label: 'Ask Aangan', run: go.ask },
        })
      }
      const due = kid.homework.filter((h) => !h.done && h.due <= addDays(snap.now.date, 1))
      if (due.length) {
        items.push({
          key: `homework-${m.id}`,
          severity: 'info',
          icon: <BookOpen className={icon} />,
          title: `${m.name} has ${due.length === 1 ? 'homework' : `${due.length} homework tasks`} due ${due.some((h) => h.due <= snap.now.date) ? 'today' : 'tomorrow'}`,
          detail: due.map((h) => `${h.subject}: ${h.task}`).join('; '),
        })
      }
    }
  }

  const failed = snap.notifications.filter((n) => n.status === 'failed').length
  if (failed) {
    items.push({
      key: 'failed',
      severity: 'warning',
      icon: <Send className={icon} />,
      title: `${failed} family ${failed === 1 ? 'message' : 'messages'} could not be delivered`,
      action: { label: 'See details', run: go.did },
    })
  }

  for (const c of clashes(snap)) {
    items.push({
      key: `clash-${c.key}`,
      severity: 'warning',
      icon: <CalendarClock className={icon} />,
      title: `Clash on ${dayLabel(c.date)}: ${c.a.title} and ${c.b.title}`,
      detail: `${joinNames(snap, c.who)} ${c.who.length === 1 ? 'is' : 'are'} booked for both.`,
      action: { label: 'Open schedule', run: go.schedule },
    })
  }

  return items.sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity])
}

function Attention({ items }: { items: AttentionItem[] }) {
  if (items.length === 0) {
    return (
      <EmptyState icon={<Check className="size-6 text-[var(--rw-text-success)]" aria-hidden="true" />} title="Nothing needs your attention">
        Everyone is on track right now.
      </EmptyState>
    )
  }
  return (
    <ListCard aria-label="Items that need your attention">
      {items.map((i) => (
        <li key={i.key} className="flex items-start gap-3 px-4 py-3.5">
          <span className={cn('mt-0.5 grid size-9 shrink-0 place-items-center rounded-full', ICON_TONE[i.severity])} aria-hidden="true">
            {i.icon}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block font-semibold">{i.title}</span>
            {i.detail && <span className="t-secondary block">{i.detail}</span>}
          </span>
          {i.action && (
            <Button size="sm" variant="secondary" className="shrink-0 self-center" onClick={i.action.run}>
              {i.action.label}
            </Button>
          )}
        </li>
      ))}
    </ListCard>
  )
}

/* ---------------------------------------------------------------------------------------------------------------------------------
 * Ask Aangan: the main thing to do on Home
 * ------------------------------------------------------------------------------------------------------------------------------ */

function AskCard() {
  const { snap, personaId, say, setTab } = useApp()
  const [text, setText] = useState('')
  const member = snap && personaId ? memberOf(snap, personaId) : undefined
  const chips = member ? suggestionsFor(member).slice(0, 3) : []

  const send = (message: string) => {
    const value = message.trim()
    if (!value) return
    void say(value)
    setText('')
    setTab('ask')
  }

  return (
    <Card className="border-[var(--selected-edge)] p-5 lg:p-6">
      <div className="flex items-start gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-full bg-brand text-brand-ink" aria-hidden="true">
          <Sparkles className="size-5" />
        </span>
        <div className="min-w-0">
          <h2 className="t-section">Ask Aangan</h2>
          <p className="t-secondary">Plan, book, remind or check on anyone in the family.</p>
        </div>
      </div>
      <form
        className="mt-4 flex items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          send(text)
        }}
      >
        <label htmlFor="home-ask" className="sr-only">
          Ask Aangan
        </label>
        <input
          id="home-ask"
          value={text}
          onChange={(e) => setText(e.target.value)}
          name="question"
          placeholder="Ask about anyone in the family…"
          autoComplete="off"
          spellCheck
          enterKeyHint="send"
          className={cn(inputClass, 'min-w-0 flex-1')}
        />
        <IconButton label="Speak to Aangan" variant="secondary" onClick={() => setTab('ask')}>
          <Mic className="size-5" />
        </IconButton>
        <Button type="submit" disabled={!text.trim()}>
          Ask
        </Button>
      </form>
      {chips.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-2" aria-label="Things you could ask">
          {chips.map((c) => (
            <li key={c}>
              <button
                type="button"
                onClick={() => send(c)}
                className="min-h-10 rounded-full border border-line bg-surface px-3.5 text-left text-sm text-ink transition-colors hover:bg-hover lg:min-h-9"
              >
                {c}
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

/* ---------------------------------------------------------------------------------------------------------------------------------
 * Aangan's impact and Spending this month
 * ------------------------------------------------------------------------------------------------------------------------------ */

const NBSP = ' '
const minutesLabel = (m: number) => {
  if (m < 60) return `${m}${NBSP}min`
  const h = Math.floor(m / 60)
  const rest = m % 60
  return rest ? `${h}${NBSP}h ${rest}${NBSP}min` : `${h}${NBSP}h`
}

/** Currency in the browser's own locale, so separators follow the reader, not a hardcoded format. */
const money = (value: number, currency: string) => {
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency, maximumFractionDigits: 0 }).format(value)
  } catch {
    return `${currency}${NBSP}${Math.round(value)}`
  }
}

function Stat({ value, label, extra }: { value: string; label: string; extra?: ReactNode }) {
  return (
    <div className="min-w-0">
      <p className="num text-3xl font-extrabold leading-none">{value}</p>
      <p className="t-secondary mt-1.5 flex items-center gap-1">
        {label}
        {extra}
      </p>
    </div>
  )
}

function ImpactCard({ result }: { result: ImpactResult }) {
  const [note, setNote] = useState(false)
  const impact: Impact | null = result.status === 'ready' ? result.impact : null
  const empty = !impact || (impact.actions === 0 && impact.minutes_saved === 0 && impact.alerts === 0)
  return (
    <Card className="flex h-full flex-col p-5">
      <h2 className="t-section">Aangan’s impact</h2>
      <p className="t-secondary">What Aangan has taken off your plate</p>
      <div className="mt-4 flex-1">
        {result.status === 'loading' ? (
          <div className="grid grid-cols-3 gap-4" role="status" aria-label="Loading impact…">
            <Skeleton className="h-14" />
            <Skeleton className="h-14" />
            <Skeleton className="h-14" />
          </div>
        ) : empty ? (
          <p className="t-secondary">Ask Aangan to book, remind or plan something, and the tally starts here.</p>
        ) : (
          <>
            <div className="grid grid-cols-3 gap-4">
              <Stat value={String(impact.actions)} label="Tasks done" />
              <Stat
                value={minutesLabel(impact.minutes_saved)}
                label="Time saved"
                extra={
                  <IconButton
                    label="How time saved is estimated"
                    aria-expanded={note}
                    className="-my-2 size-9 lg:size-7"
                    onClick={() => setNote((v) => !v)}
                  >
                    <Info className="size-4" />
                  </IconButton>
                }
              />
              <Stat value={String(impact.alerts)} label="Alerts raised" />
            </div>
            <p className="t-caption mt-3">Time saved is an estimate.</p>
            {note && (
              <div className="mt-2 rounded-lg bg-surface-3 p-3 text-sm" role="note">
                <p className="font-semibold">How it is estimated</p>
                {impact.assumptions.length > 0 ? (
                  <ul className="mt-1 list-disc space-y-0.5 pl-5">
                    {impact.assumptions.map((a) => (
                      <li key={a}>{a}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="t-secondary mt-1">Based on the typical time each kind of task takes by hand.</p>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </Card>
  )
}

function SpendingCard({ result, onTell }: { result: ImpactResult; onTell: () => void }) {
  const m: Money | null = result.status === 'ready' ? result.impact.money : null
  const hasSpend = m !== null && m.month_total > 0
  const budget = m?.budget_total ?? null
  const ratio = hasSpend && budget ? m.month_total / budget : 0
  return (
    <Card className="flex h-full flex-col p-5">
      <h2 className="t-section">Spending this month</h2>
      <p className="t-secondary">What the family has spent through Aangan</p>
      <div className="mt-4 flex-1">
        {result.status === 'loading' ? (
          <Skeleton className="h-20" />
        ) : !hasSpend || !m ? (
          <div className="flex items-start gap-3">
            <span className="grid size-10 shrink-0 place-items-center rounded-full bg-surface-2 text-ink-2" aria-hidden="true">
              <Wallet className="size-5" />
            </span>
            <div className="min-w-0">
              <p className="text-sm">
                Tell Aangan what you spent: <span className="font-semibold">“I spent 450 on groceries”</span>
              </p>
              <Button size="sm" variant="secondary" className="mt-3" onClick={onTell}>
                Tell Aangan
              </Button>
            </div>
          </div>
        ) : (
          <>
            <p className="num text-3xl font-extrabold leading-none">{money(m.month_total, m.currency)}</p>
            {budget ? (
              <div className="mt-4">
                <div
                  role="progressbar"
                  aria-label="Budget used"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={Math.min(100, Math.round(ratio * 100))}
                  className="h-2 overflow-hidden rounded-full bg-surface-2"
                >
                  <div
                    className={cn('h-full rounded-full', ratio >= 1 ? 'bg-[var(--rw-danger)]' : ratio >= 0.8 ? 'bg-[var(--rw-warning)]' : 'bg-brand')}
                    style={{ width: `${Math.min(100, ratio * 100)}%` }}
                  />
                </div>
                <p className="t-secondary num mt-1.5">
                  {m.budget_left !== null && m.budget_left < 0
                    ? `${money(-m.budget_left, m.currency)} over a budget of ${money(budget, m.currency)}`
                    : `${money(m.budget_left ?? Math.max(0, budget - m.month_total), m.currency)} left of ${money(budget, m.currency)}`}
                </p>
              </div>
            ) : (
              <p className="t-secondary mt-1.5">No budget set yet.</p>
            )}
            {m.top_tip && (
              <div className="mt-4 flex items-start gap-2.5 rounded-lg bg-info-bg p-3 text-sm">
                <Lightbulb className="mt-0.5 size-4 shrink-0 text-info" aria-hidden="true" />
                <p>
                  {m.top_tip}
                  {m.potential_savings > 0 && <span className="font-semibold"> You could save about {money(m.potential_savings, m.currency)}.</span>}
                </p>
              </div>
            )}
          </>
        )}
      </div>
    </Card>
  )
}

/* ---------------------------------------------------------------------------------------------------------------------------------
 * Recent actions
 * ------------------------------------------------------------------------------------------------------------------------------ */

function RecentActions({ snap, onSeeAll }: { snap: Snapshot; onSeeAll: () => void }) {
  const recent = snap.events
    .map((e) => describeEvent(e, snap))
    .filter((d) => d.kind === 'action')
    .slice(-3)
    .reverse()
  return (
    <section>
      <SectionHeader
        title="Recent actions"
        hint="What Aangan did lately"
        action={
          recent.length > 0 ? (
            <Button size="sm" variant="tertiary" onClick={onSeeAll}>
              See all
            </Button>
          ) : undefined
        }
      />
      {recent.length === 0 ? (
        <EmptyState icon={<Sparkles className="size-6" aria-hidden="true" />} title="Nothing yet">
          When Aangan books, reminds or plans something, it shows up here.
        </EmptyState>
      ) : (
        <ListCard aria-label="Recent actions">
          {recent.map((d) => (
            <ListRow
              key={d.id}
              title={d.text}
              subtitle={d.ok ? undefined : d.reason}
              meta={d.ts.slice(0, 5)}
              trailing={d.ok ? <AgentBadge agent={d.agent} /> : <Pill tone="danger">Did not work</Pill>}
            />
          ))}
        </ListCard>
      )}
    </section>
  )
}

/* ---------------------------------------------------------------------------------------------------------------------------------
 * Home
 * ------------------------------------------------------------------------------------------------------------------------------ */

const longDate = (iso: string) => {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'UTC' })
}

export function Home() {
  const { snap, personaId, setTab, callTool } = useApp()
  const impact = useImpact(snap ? `${snap.events.length}:${snap.notifications.length}` : 'none')
  if (!snap) return null
  const me = personaId ? memberOf(snap, personaId) : undefined
  const hour = Number(snap.now.time.slice(0, 2))
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'
  const all = buildAttention(snap, {
    ask: () => setTab('ask'),
    schedule: () => setTab('family', 'schedule'),
    did: () => setTab('ask', 'did'),
    refill: (memberId, med) => void callTool('care', 'order_refill', { member_id: memberId, med_name: med }, `Refill for ${med} ordered.`),
  })
  const top = all.slice(0, TOP_ITEMS)

  return (
    <div className="mx-auto max-w-[1100px] space-y-8 p-4 pb-10 lg:space-y-10 lg:p-8">
      <header>
        <h1 className="t-page">{me ? `${greeting}, ${me.name.split(' ')[0]}` : greeting}</h1>
        <p className="t-secondary mt-1">{longDate(snap.now.date)}</p>
      </header>

      <AskCard />

      <PlanTogetherCard />

      <section>
        <SectionHeader title="Needs your attention" hint={all.length > TOP_ITEMS ? `The ${TOP_ITEMS} most important of ${all.length}` : undefined} />
        <Attention items={top} />
      </section>

      <div className="grid gap-6 lg:grid-cols-2 lg:gap-8">
        <ImpactCard result={impact} />
        <SpendingCard result={impact} onTell={() => setTab('ask')} />
      </div>

      <RecentActions snap={snap} onSeeAll={() => setTab('ask', 'did')} />
    </div>
  )
}
