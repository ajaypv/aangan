import type { Participant, Room } from '@/types'
import { ApprovalCard } from './board/ApprovalCard'
import { FlightsCard } from './board/FlightsCard'
import { HotelsCard } from './board/HotelsCard'
import { ItineraryCard } from './board/ItineraryCard'
import { BookingsCard, ChecklistCard, CostsCard, DecisionsCard, QuestionsCard } from './board/ListCards'
import { MapCard } from './board/MapCard'
import { PlacesCard } from './board/PlacesCard'
import { RestaurantsCard } from './board/RestaurantsCard'
import { SummaryCard } from './board/SummaryCard'

/**
 * The plan board, in reading order: trip summary with the cost strip, the pending approval, the day-by-day itinerary (the centrepiece),
 * places to visit, where to eat, flights, hotels, the map, then costs, decisions, open questions, the checklist and bookings.
 * From 1280px the map stays in view beside the itinerary and the cards that feed it; below that it sits after the hotels.
 */
export function PlanBoard({ room, me, onDecide }: { room: Room; me: Participant | undefined; onDecide: (approve: boolean) => Promise<string | null> }) {
  return (
    <div className="mx-auto grid max-w-[1200px] gap-4 p-3 pb-8 sm:p-4 lg:p-5 lg:pb-10">
      <SummaryCard room={room} />
      <ApprovalCard room={room} me={me} onDecide={onDecide} />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(320px,0.78fr)] xl:items-start">
        <div className="grid min-w-0 gap-4">
          <ItineraryCard room={room} />
          <PlacesCard room={room} />
          <RestaurantsCard room={room} />
          <FlightsCard room={room} />
          <HotelsCard room={room} />
        </div>
        <div className="min-w-0 xl:sticky xl:top-4">
          <MapCard room={room} />
        </div>
      </div>
      <CostsCard room={room} />
      <DecisionsCard room={room} />
      <QuestionsCard room={room} />
      <ChecklistCard room={room} />
      <BookingsCard room={room} />
    </div>
  )
}
