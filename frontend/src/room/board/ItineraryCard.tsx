import { CalendarDays } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ItineraryItem, Room } from '@/types'
import { dayLabel, money, tripDays } from '../format'
import { useFlash } from '../useBoardFlash'
import { kindOf } from './kinds'
import { BoardCard, EmptyLine, FlashItem } from './shared'

/**
 * The centrepiece: Day 1, Day 2 and so on. Each day interleaves travel, places and meals in time order and shows what that day costs
 * (from `cost_summary.by_day`). Days of the trip with nothing yet say so rather than disappearing.
 */
export function ItineraryCard({ room, day: selectedDay = null, onDayChange }: { room: Room; day?: number | null; onDayChange?: (day: number | null) => void }) {
  const { items: changedItems } = useFlash()
  const { itinerary, dates, cost_summary: sum } = room.plan
  const currency = sum.currency
  const byDay = new Map<number, ItineraryItem[]>()
  for (const i of itinerary) byDay.set(i.day, [...(byDay.get(i.day) ?? []), i])
  const lastDay = Math.max(0, ...byDay.keys(), dates ? tripDays(dates.start, dates.end) : 0)
  const days = Array.from({ length: lastDay }, (_, k) => k + 1)
  const dateOf = (day: number) => byDay.get(day)?.[0]?.date ?? sum.by_day.find((d) => d.day === day)?.date

  return (
    <BoardCard id="itinerary" section="itinerary" title="Day by day" icon={<CalendarDays className="size-4" />} count={days.length}>
      {days.length > 0 && onDayChange && (
        <div className="room-day-picker" role="group" aria-label="Show itinerary day">
          <button type="button" aria-pressed={selectedDay === null} onClick={() => onDayChange(null)}>All days</button>
          {days.map((day) => (
            <button key={day} type="button" aria-pressed={selectedDay === day} onClick={() => onDayChange(day)}>
              Day {day}
              {byDay.get(day)?.some((item) => changedItems.has(item.id)) && <span className="room-day-dot" role="img" aria-label={`Day ${day} updated`} />}
            </button>
          ))}
        </div>
      )}
      {itinerary.length === 0 ? (
        <EmptyLine>The day-by-day plan appears once you decide what to do.</EmptyLine>
      ) : (
        <ol className="space-y-5 px-4 pb-4 pt-2" aria-label="Itinerary by day">
          {days.filter((day) => selectedDay === null || day === selectedDay).map((day) => {
            const items = [...(byDay.get(day) ?? [])].sort((a, b) => a.time.localeCompare(b.time))
            const date = dateOf(day)
            const cost = sum.by_day.find((d) => d.day === day)?.amount
            return (
              <li key={day} data-day={day}>
                <div className="sticky top-0 z-[1] -mx-4 flex items-baseline justify-between gap-3 border-b border-line bg-surface px-4 pb-1.5 pt-1">
                  <h4 className="font-bold">
                    Day {day}
                    {date && <span className="t-secondary ml-2 font-normal">{dayLabel(date)}</span>}
                  </h4>
                  {cost ? (
                    <p className="num text-sm font-semibold" aria-label={`Cost for day ${day}`}>
                      {money(cost, currency)}
                    </p>
                  ) : null}
                </div>
                {items.length === 0 ? (
                  <p className="t-secondary pt-2">Nothing planned yet for this day.</p>
                ) : (
                  <ul className="mt-2">
                    {items.map((it, idx) => {
                      const k = kindOf(it.kind)
                      const Icon = k.icon
                      return (
                        <FlashItem key={it.id} id={it.id} className="room-itinerary-item relative flex gap-3 rounded-md py-1.5 pl-1">
                          <p className="num w-11 shrink-0 pt-1.5 text-sm font-semibold text-ink-2">{it.time}</p>
                          <span className="relative flex shrink-0 flex-col items-center" aria-hidden="true">
                            <span className={cn('room-itinerary-node z-[0] grid size-8 place-items-center rounded-full', k.tone)}>
                              <Icon className="size-4" />
                            </span>
                            {idx < items.length - 1 && <span className="room-itinerary-connector mt-0.5 w-px flex-1 bg-edge" />}
                          </span>
                          <div className="min-w-0 flex-1 pb-1.5">
                            <p className="font-semibold leading-snug">
                              <span className="sr-only">{k.label}: </span>
                              {it.title}
                            </p>
                            <p className="t-secondary">{it.place}</p>
                            {it.notes && <p className="t-caption mt-0.5">{it.notes}</p>}
                          </div>
                          {typeof it.cost === 'number' && it.cost > 0 && <p className="num shrink-0 pt-1.5 text-sm text-ink-2">{money(it.cost, currency)}</p>}
                        </FlashItem>
                      )
                    })}
                  </ul>
                )}
              </li>
            )
          })}
        </ol>
      )}
    </BoardCard>
  )
}
