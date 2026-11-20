import { AlertTriangle, CalendarCheck, Pill as PillIcon, School, UserRound } from 'lucide-react'
import type { ReactNode } from 'react'
import { dosesToday, factsOf, factTone, kidOf, marksInOrder, nextEvents, schoolToday, seniorOf } from '@/lib/domain'
import { dayLabel, joinNames, memberOf, minutes } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Member, Snapshot } from '@/types'
import { Avatar, Button, Card, CardFooter, EmptyState, ListCard, MemberDots, Pill, type Tone } from './primitives'

/*
 * The family board and today's timeline. They used to be on Home; the Family tab shows them now.
 * Both take the snapshot and render real data only.
 */

/** Today across the family: one row per event, with who is in it, and a "Now" or "Next" marker. */
export function TodayTimeline({ snap, onSeeWeek }: { snap: Snapshot; onSeeWeek?: () => void }) {
  const today = snap.calendar.filter((e) => e.date === snap.now.date).sort((a, b) => a.start.localeCompare(b.start))
  if (today.length === 0) {
    return (
      <EmptyState icon={<CalendarCheck className="size-6" aria-hidden="true" />} title="A quiet day">
        Nothing is scheduled for anyone today.
      </EmptyState>
    )
  }
  const now = minutes(snap.now.time)
  const nextId = today.find((e) => minutes(e.start) > now)?.id
  return (
    <div>
      <ListCard aria-label="Today's schedule">
        {today.map((e) => {
          const over = minutes(e.end) <= now
          const live = minutes(e.start) <= now && now < minutes(e.end)
          const people = e.member_ids.map((id) => memberOf(snap, id)).filter((m): m is Member => Boolean(m))
          return (
            <li key={e.id} className="flex items-center gap-3 px-4 py-3">
              <span className="num w-14 shrink-0">
                <span className={cn('block font-bold', over && 'text-ink-2')}>{e.start}</span>
                <span className="t-caption block">{e.end}</span>
              </span>
              <span className="min-w-0 flex-1">
                <span className={cn('block truncate font-semibold', over && 'text-ink-2')}>{e.title}</span>
                <span className="t-secondary block truncate">{joinNames(snap, e.member_ids)}</span>
              </span>
              <span className="flex shrink-0 flex-col items-end gap-1.5">
                {live && <Pill tone="brand">Now</Pill>}
                {!live && e.id === nextId && <Pill tone="info">Next</Pill>}
                <MemberDots members={people} />
              </span>
            </li>
          )
        })}
      </ListCard>
      {onSeeWeek && (
        <div className="mt-2 flex justify-end">
          <Button size="sm" variant="tertiary" onClick={onSeeWeek}>
            See the week
          </Button>
        </div>
      )}
    </div>
  )
}

function statusOf(snap: Snapshot, m: Member): { tone: Tone; icon: ReactNode; text: string; extra?: { tone: Tone; text: string } } {
  const iconClass = 'size-3.5'
  const kid = kidOf(snap, m.id)
  if (m.kind === 'child' && kid) {
    const school = schoolToday(snap, m.id)
    const atSchool = kid.status === 'at_school'
    const late = !atSchool && school !== undefined && minutes(snap.now.time) > minutes(school.start) && minutes(snap.now.time) < minutes(school.end)
    const last = marksInOrder(kid).at(-1)
    return {
      tone: atSchool ? 'success' : late ? 'warning' : 'neutral',
      icon: <School className={iconClass} />,
      text: atSchool ? `At school since ${kid.arrived_at ?? 'today'}` : late ? 'Not at school yet' : 'At home',
      extra: last ? { tone: 'neutral', text: `Latest: ${last.subject} ${last.score}/${last.max}` } : undefined,
    }
  }
  const senior = seniorOf(snap, m.id)
  if (m.kind === 'senior' && senior) {
    const doses = dosesToday(snap, senior)
    const taken = doses.filter((d) => d.status === 'taken').length
    const missed = doses.some((d) => d.status === 'missed')
    const low = senior.meds.find((x) => x.stock_days <= 3)
    return {
      tone: missed ? 'danger' : doses.length > 0 && taken === doses.length ? 'success' : 'neutral',
      icon: <PillIcon className={iconClass} />,
      text: doses.length ? `${taken} of ${doses.length} doses taken` : 'No medicines scheduled',
      extra: low ? { tone: 'warning', text: `${low.name}: ${low.stock_days} days left` } : undefined,
    }
  }
  const now = minutes(snap.now.time)
  const todays = snap.calendar.filter((e) => e.date === snap.now.date && e.member_ids.includes(m.id))
  const live = todays.find((e) => minutes(e.start) <= now && now < minutes(e.end))
  const later = todays.filter((e) => minutes(e.start) > now).length
  return {
    tone: live ? 'info' : 'neutral',
    icon: <UserRound className={iconClass} />,
    text: live ? `In ${live.title} until ${live.end}` : later ? `${later} more ${later === 1 ? 'event' : 'events'} today` : 'Nothing else today',
  }
}

/** A compact card per person: status line, anything to be careful about, and the next thing in their day. */
export function MemberCard({ snap, member, onOpen }: { snap: Snapshot; member: Member; onOpen?: (m: Member) => void }) {
  const status = statusOf(snap, member)
  const flagged = factsOf(snap, member.id).filter((f) => factTone(f) !== 'neutral')
  const upcoming = nextEvents(snap, member.id, 1)[0]
  return (
    <Card as="article" aria-label={member.name} className="flex flex-col">
      <div className="flex items-center gap-3 p-4 pb-2">
        <Avatar member={member} size={44} />
        <div className="min-w-0 flex-1">
          <h3 className="t-card truncate">{member.name}</h3>
          <p className="t-secondary truncate">
            {member.relation} · {member.age}
          </p>
        </div>
      </div>
      <div className="space-y-2 px-4 pb-3">
        <div className="flex flex-wrap items-center gap-1.5">
          <Pill tone={status.tone}>
            {status.icon}
            {status.text}
          </Pill>
          {status.extra && <Pill tone={status.extra.tone}>{status.extra.text}</Pill>}
        </div>
        {flagged.length > 0 && (
          <ul className="flex flex-wrap gap-1.5" aria-label={`What Aangan remembers about ${member.name}`}>
            {flagged.slice(0, 3).map((f) => (
              <li key={f.id}>
                <Pill tone={factTone(f)}>
                  {f.tags.includes('allergy') && <AlertTriangle className="size-3" aria-hidden="true" />}
                  {f.fact}
                </Pill>
              </li>
            ))}
          </ul>
        )}
      </div>
      {upcoming && (
        <p className="mt-auto flex items-baseline justify-between gap-3 border-t border-line px-4 py-2.5 text-sm">
          <span className="min-w-0 truncate font-medium">{upcoming.title}</span>
          <span className="num t-secondary shrink-0">
            {upcoming.date === snap.now.date ? 'Today' : dayLabel(upcoming.date)} {upcoming.start}
          </span>
        </p>
      )}
      {onOpen && (
        <CardFooter className={cn(!upcoming && 'mt-auto')}>
          <Button size="sm" variant="tertiary" className="ml-auto" onClick={() => onOpen(member)}>
            Open {member.name}
          </Button>
        </CardFooter>
      )}
    </Card>
  )
}

/** All the cards, in a responsive grid. */
export function FamilyBoard({ snap, onOpen }: { snap: Snapshot; onOpen?: (m: Member) => void }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {snap.members.map((m) => (
        <MemberCard key={m.id} snap={snap} member={m} onOpen={onOpen} />
      ))}
    </div>
  )
}
