import { ChevronDown, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { useMediaQuery } from '@/lib/useMediaQuery'
import type { Participant, Room } from '@/types'
import { tripDays } from './format'
import { useFlash, type SectionKey } from './useBoardFlash'
import { ApprovalCard } from './board/ApprovalCard'
import { FlightsCard } from './board/FlightsCard'
import { HotelsCard } from './board/HotelsCard'
import { ItineraryCard } from './board/ItineraryCard'
import { BookingsCard, ChecklistCard, CostsCard, DecisionsCard, QuestionsCard } from './board/ListCards'
import { MapCard } from './board/MapCard'
import { PlacesCard } from './board/PlacesCard'
import { RestaurantsCard } from './board/RestaurantsCard'
import { SummaryCard } from './board/SummaryCard'
import { TransportCard } from './board/TransportCard'

const SECTION_LABELS: Record<SectionKey, string> = {
  summary: 'trip details', approval: 'approval', flights: 'flights', transport: 'train, bus and car', hotels: 'stays', map: 'route',
  itinerary: 'itinerary', places: 'places', restaurants: 'food', costs: 'budget',
  decisions: 'decisions', questions: 'questions', checklist: 'checklist', bookings: 'bookings',
}

export function PlanBoard({ room, me, onDecide }: { room: Room; me: Participant | undefined; onDecide: (approve: boolean) => Promise<string | null> }) {
  const wide = useMediaQuery('(min-width: 1024px)')
  const [selectedDay, setSelectedDay] = useState<number | null>(1)
  const dayCount = Math.max(0, ...room.plan.itinerary.map((item) => item.day), room.plan.dates ? tripDays(room.plan.dates.start, room.plan.dates.end) : 0)
  const activeDay = wide && selectedDay !== null && dayCount > 0 ? Math.min(selectedDay, dayCount) : null
  const { sections } = useFlash()
  const updated = (Object.keys(SECTION_LABELS) as SectionKey[]).filter((key) => sections.has(key))
  const openQuestions = room.plan.open_questions.some((q) => !q.resolved)
  const optionsChanged = updated.some((key) => !['summary', 'approval', 'itinerary', 'map', ...(openQuestions ? ['questions'] : [])].includes(key))

  return (
    <div className="room-plan-board mx-auto grid max-w-[1600px] gap-4 p-3 pb-8 sm:p-4 lg:p-5 lg:pb-10">
      <SummaryCard room={room} />
      <ApprovalCard room={room} me={me} onDecide={onDecide} />
      {!wide && openQuestions && <QuestionsCard room={room} />}
      <div className="room-plan-update" role="status" aria-live="polite" aria-atomic="true">
        <Sparkles className="size-4 shrink-0" aria-hidden="true" />
        <span>{updated.length ? `Just updated: ${updated.map((key) => SECTION_LABELS[key]).join(', ')}.` : 'Your trip, taking shape as you talk.'}</span>
      </div>
      <div className="room-plan-canvas">
        <div className="min-w-0">
          <ItineraryCard room={room} day={activeDay} onDayChange={setSelectedDay} />
        </div>
        <div className="room-map-column min-w-0">
          <MapCard room={room} day={activeDay} />
        </div>
      </div>
      <details className="room-plan-options" open={!wide}>
        <summary>
          <div className="min-w-0 flex-1">
            <h2 className="font-semibold">Options, decisions &amp; trip details</h2>
            <p className="t-caption">{room.plan.flights.length} flights · {room.plan.transport.length > 0 && `${room.plan.transport.length} train, bus and car · `}{room.plan.hotels.length} stays · {room.plan.places.length} places · {room.plan.restaurants.length} places to eat</p>
          </div>
          {optionsChanged && <span className="room-updated-badge">Updated</span>}
          <ChevronDown className="room-details-chevron size-4 shrink-0" aria-hidden="true" />
        </summary>
        <div className="room-options-grid">
          <FlightsCard room={room} />
          <TransportCard room={room} />
          <HotelsCard room={room} />
          <PlacesCard room={room} />
          <RestaurantsCard room={room} />
          <DecisionsCard room={room} />
          {!openQuestions && <QuestionsCard room={room} />}
          <ChecklistCard room={room} />
          <CostsCard room={room} />
          <BookingsCard room={room} />
        </div>
      </details>
    </div>
  )
}
