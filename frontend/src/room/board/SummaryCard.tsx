import { ArrowRight, Calendar, MapPin, Sparkles } from 'lucide-react'
import type { Room } from '@/types'
import { Avatar, Pill } from '@/ui/primitives'
import { avatarOf, dateRange, participantById, plural, tripDays } from '../format'
import { CostStrip } from './CostStrip'
import { BoardCard, EmptyLine } from './shared'

/** The goal, where and when, who is coming, and the budget meter against the costs so far. */
export function SummaryCard({ room }: { room: Room }) {
  const p = room.plan
  const travellers = p.travelers.map((id) => participantById(room, id)).filter((x): x is NonNullable<typeof x> => Boolean(x))
  const empty = !p.goal && !p.destination && !p.dates && travellers.length === 0 && !p.budget && p.cost_summary.total === 0

  return (
    <BoardCard id="summary" section="summary" title="Trip summary" icon={<Sparkles className="size-4" />}>
      {empty ? (
        <EmptyLine>Say where you want to go and Aangan will start the plan.</EmptyLine>
      ) : (
        <div className="space-y-4 px-4 pb-4 pt-2">
          <div>
            <p className="text-xl font-bold leading-snug">{p.goal || room.title}</p>
            <ul className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-sm text-ink-2" aria-label="Where and when">
              {(p.origin || p.destination) && (
                <li className="inline-flex items-center gap-1.5">
                  <MapPin className="size-4 shrink-0" aria-hidden="true" />
                  {p.origin && <span>{p.origin.name}</span>}
                  {p.origin && p.destination && <ArrowRight className="size-3.5" aria-label="to" />}
                  {p.destination && <span className="font-semibold text-ink">{p.destination.name}</span>}
                </li>
              )}
              {p.dates && (
                <li className="inline-flex items-center gap-1.5">
                  <Calendar className="size-4 shrink-0" aria-hidden="true" />
                  <span className="num">
                    {dateRange(p.dates.start, p.dates.end)} ({plural(tripDays(p.dates.start, p.dates.end), 'day')})
                  </span>
                </li>
              )}
            </ul>
          </div>

          <CostStrip room={room} />

          {travellers.length > 0 && (
            <div>
              <p className="t-caption mb-1.5 font-semibold uppercase tracking-wide">Travelling</p>
              <ul className="flex flex-wrap gap-2" aria-label="Travellers">
                {travellers.map((t) => (
                  <li key={t.id} className="inline-flex items-center gap-2 rounded-full border border-line bg-surface py-0.5 pl-0.5 pr-3 text-sm">
                    <Avatar member={avatarOf(t)} size={26} />
                    <span className="max-w-32 truncate">{t.name}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {p.preferences.length > 0 && (
            <ul className="flex flex-wrap gap-1.5" aria-label="Preferences">
              {p.preferences.map((x) => (
                <li key={x}>
                  <Pill tone="info">{x}</Pill>
                </li>
              ))}
            </ul>
          )}

        </div>
      )}
    </BoardCard>
  )
}
