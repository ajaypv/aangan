# Family Room: contract between backend and frontend

Goal (hackathon, one day): several people join one **room** to plan something together, usually a trip. They talk (text, voice, optional camera).
Aangan keeps a live **plan** from the discussion, can search and "book" with tools, and everyone sees the plan on a board that updates by itself.
Anything that spends money needs a human tap to approve. Bookings in this build are demo bookings and are labelled as such.

Everything below is the agreed shape. Backend and frontend are built against it separately. Do not change a field name without changing this file.

## Room state (what `GET /api/rooms/{id}` returns)

```json
{
  "id": "r-7f3a9c",
  "version": 12,
  "title": "Goa trip",
  "host_participant_id": "p-1",
  "created_at": "2026-11-20 19:05",
  "participants": [
    {"id": "p-1", "name": "Priya", "member_id": "priya", "guest": false, "rtc_uid": 41231, "joined_at": "19:05", "last_seen": "19:12", "online": true},
    {"id": "p-2", "name": "Meera (guest)", "member_id": null, "guest": true, "rtc_uid": 41232, "joined_at": "19:07", "last_seen": "19:11", "online": true}
  ],
  "messages": [
    {"id": 1, "kind": "user", "participant_id": "p-1", "name": "Priya", "text": "Let's do Goa over Christmas, five days.", "ts": "19:06", "lang": "en"},
    {"id": 2, "kind": "agent", "participant_id": null, "name": "Aangan", "text": "Goa for five days from the twenty sixth. Who is coming?", "ts": "19:06", "lang": "en"},
    {"id": 3, "kind": "system", "participant_id": null, "name": "", "text": "Aangan added 2 flight options", "ts": "19:07", "lang": "en"}
  ],
  "plan": {
    "goal": "Family trip to Goa",
    "destination": {"name": "Goa", "lat": 15.2993, "lon": 74.124},
    "origin": {"name": "Bengaluru", "lat": 12.9716, "lon": 77.5946},
    "dates": {"start": "2026-12-26", "end": "2026-12-30"},
    "travelers": ["p-1", "p-2"],
    "budget": {"total": 80000, "currency": "INR"},
    "preferences": ["Dadi needs step-free access", "Aarav: no peanuts"],
    "flights": [
      {"id": "f-1", "airline": "IndiGo", "number": "6E-512", "from": "BLR", "to": "GOI", "date": "2026-12-26", "dep": "07:10", "arr": "08:30",
       "price": 4200, "per": "person", "stops": 0, "source": "live", "link": null, "status": "proposed"}
    ],
    "hotels": [
      {"id": "h-1", "name": "Coconut Grove Resort", "area": "Candolim", "price_per_night": 6500, "rating": 4.4, "lat": 15.5183, "lon": 73.7620,
       "step_free": true, "source": "sample", "status": "proposed"}
    ],
    "itinerary": [
      {"id": "i-1", "day": 1, "date": "2026-12-26", "time": "10:00", "title": "Check in and lunch", "place": "Candolim", "lat": 15.5183, "lon": 73.762, "notes": ""}
    ],
    "costs": [
      {"label": "Flights (4 travellers)", "amount": 16800, "status": "estimate"},
      {"label": "Hotel (4 nights)", "amount": 26000, "status": "estimate"}
    ],
    "decisions": [{"id": "d-1", "text": "Fly on the 26th morning", "by": ["p-1", "p-2"], "ts": "19:09"}],
    "open_questions": [{"id": "q-1", "text": "How many rooms do we need?", "asked_by": "Aangan", "ts": "19:10", "resolved": false}],
    "checklist": [{"id": "c-1", "text": "Check Dadi's medicine stock before travel", "done": false, "owner": null}]
  },
  "pending_approval": {
    "id": "a-1",
    "kind": "booking",
    "title": "Book IndiGo 6E-512 for 4 people",
    "summary": "4 seats BLR to GOI on 26 Dec 07:10, 16,800 total. Demo booking: no real money moves.",
    "amount": 16800,
    "items": ["f-1"],
    "needs": "host",
    "approvals": [],
    "status": "waiting"
  },
  "bookings": [
    {"id": "b-1", "kind": "flight", "ref": "DEMO-4F2K9", "title": "IndiGo 6E-512, 26 Dec 07:10, 4 travellers", "amount": 16800, "demo": true, "ts": "19:14"}
  ],
  "agent": {"live": false, "voice_session": null}
}
```

Rules:
- `version` is an integer that increases on every change (a message, a plan change, a join, an approval). Clients poll with `since`.
- `status` of a flight or hotel: `proposed`, `selected`, `booked`, `rejected`.
- `source` of a flight or hotel: `live` (real search result), `sample` (built-in sample data). The UI must show a small "Live" or "Sample" chip.
- `pending_approval` is `null` when nothing waits. `kind` is `booking` or `other`. `needs` is `host` or `anyone`. `status` is `waiting`, `approved`, `declined`.
- Times are `HH:MM` in India time, dates are `YYYY-MM-DD`, money is a whole number of rupees.
- Every list can be empty. `plan.destination`, `plan.origin`, `plan.dates`, `plan.budget` can be `null` until said.
- Ids are strings, unique inside the room.

## Endpoints (all under `/api`, JSON)

| Method and path | Body | Returns |
|---|---|---|
| `POST /rooms` | `{"title": "Goa trip", "member_id": "priya"}` | the room state; the creator is the host and is already a participant (its id is `host_participant_id`) |
| `GET /rooms/{id}?since=N` | | the room state; if `since` equals the current `version`, returns `{"id": "...", "version": N, "unchanged": true}` |
| `POST /rooms/{id}/join` | `{"member_id": "rahul"}` or `{"guest_name": "Meera"}` | `{"participant": {...}, "room": {...}}`; joining again with the same `member_id` returns the same participant |
| `POST /rooms/{id}/heartbeat` | `{"participant_id": "p-2"}` | `{"ok": true}`; marks `last_seen`; `online` is true for 20 seconds after the last heartbeat or message |
| `POST /rooms/{id}/message` | `{"participant_id": "p-1", "text": "..."}` | the room state straight away (the message is in it); planning then runs in the background and the room `version` goes up when it finishes |
| `POST /rooms/{id}/approve` | `{"participant_id": "p-1", "approve": true}` | the room state; approving a pending booking records it in `bookings`, marks the flight or hotel `booked`, and adds a system message; declining clears it |
| `POST /rooms/{id}/rtc` | `{"participant_id": "p-1"}` | `{"app_id": "...", "channel": "room-r-7f3a9c", "token": "...", "uid": 41231, "rtm_token": "...", "rtm_user_id": "41231"}` |
| `POST /rooms/{id}/agent/start` | `{"participant_id": "p-1"}` | `{"agent_id": "...", "agent_uid": "123456", "greeting": "..."}`; Aangan joins the room's channel as a voice participant |
| `POST /rooms/{id}/agent/stop` | `{}` | `{"stopped": true}` |
| `POST /rooms/{id}/reset-plan` | `{}` | the room state with an empty plan (for rehearsing the demo) |

Errors: `404 {"detail": "unknown room"}`, `404 unknown participant`, `409 {"error": "no_household"}` is not used by rooms (guests can join a room without a household, but creating a room needs a household).

The voice agent talks to the room through the existing OpenAI-compatible endpoint:
`POST /v1/chat/completions?member=<member_id>&room=<room_id>&participant=<participant_id>`. With `room` present, the same planning brain answers and updates the plan.

## How Aangan behaves in a room

1. Every human message (typed or spoken) is saved in `messages`.
2. After a human message, a **planner** runs in the background (never blocks the HTTP reply). It reads the recent discussion and the current plan and updates the plan with tools: set goal, dates, destination, budget, travellers, preferences, search flights, search hotels, add itinerary items, add costs, record a decision, add or resolve an open question, add a checklist item, request approval for a booking.
3. Aangan **speaks in the chat** only when addressed: the text contains "Aangan" or "@Aangan", or the message is a question to it, or it was sent with the Ask button (`"ask": true` is optional in the message body). Otherwise it stays silent and only updates the plan, adding a short `system` message such as "Aangan added 2 flight options" when something visible changed.
4. Money: the planner may **propose** a booking (sets `pending_approval`) but never books by itself. Only `POST /approve` books. Bookings are demo bookings (`"demo": true`), with a reference like `DEMO-4F2K9`.
5. The planner and the voice agent share one brain, so what is said aloud and what is typed end up in the same plan.
6. The plan must never contain made-up facts about live data: flights and hotels come from tools, with `source` set honestly.

## Frontend behaviour

- A room opens at the address `?room=<id>` (the invite link). Someone without a profile on this device joins as a guest with a name.
- The room screen has: a header (title, who is here, copy-invite-link), a strip of video tiles (camera and microphone toggles, off by default until tapped), the **plan board**, and the **conversation** with a message box and a mic button. On a phone the board and the conversation are two tabs of one screen; on a wide screen they sit side by side.
- The plan board shows, in this order: the goal with dates and travellers, the pending approval (Approve and Decline buttons, price clearly shown), flights, hotels, a map with markers and the route, the day-by-day itinerary, costs against the budget, decisions, open questions, checklist, and bookings. Empty parts show a calm prompt, not a blank.
- Updates appear on their own (polling `GET /rooms/{id}?since=` about every 1.2 seconds while the screen is visible); a changed card briefly highlights.
- "Live" and "Sample" chips on flights and hotels; "Demo booking" on every booking.
- Video and audio use Agora's Web SDK (`agora-rtc-sdk-ng`, already installed) with the token from `POST /rooms/{id}/rtc`. Video is capped at 360p (profile `360p_7`) because Agora bills video by combined pixels. Aangan's voice agent, when started, is the remote user with uid `agent_uid`.
- Aangan has a panda companion card above the chat, visible during both text and voice planning (and above the Plan / Chat tabs on phones). Existing RTC speaker activity drives listening and speaking poses; voice connection problems are labelled rather than shown as listening. New messages trigger brief thinking/reply reactions, actual board changes trigger map-scribbling, and pending approvals show a waiting-for-you pose. Thinking is a bounded, 10-second visual reaction, not a claim that the backend is still working: the API has no planner-busy field. Loading old history does not replay reactions.
- The panda looks toward the pointer within its illustration and waves when clicked or keyboard-activated. These are visual interactions only: they never enable a microphone or camera. Reduced-motion preferences disable animation and pointer tracking while retaining static poses and text labels. Chat replies use the same panda face.

---

# ADDENDUM 1 (added while building): places to visit, restaurants, costs, desktop layout

The plan Aangan builds from the discussion must answer, at a glance: **where we go, which places we visit, where we eat, which days, and what it all costs.**

## New plan fields (add to `plan`; every list can be empty)

```json
"places": [
  {"id": "pl-1", "name": "Basilica of Bom Jesus", "area": "Old Goa", "category": "sight", "lat": 15.5009, "lon": 73.9116,
   "duration_min": 60, "price": 0, "per": "person", "day": 2, "notes": "Step-free ramp at the side entrance", "source": "sample", "status": "proposed"}
],
"restaurants": [
  {"id": "r-1", "name": "Vinayak Family Restaurant", "cuisine": "Goan", "area": "Assagao", "meal": "lunch", "day": 2, "date": "2026-12-27", "time": "13:00",
   "price_for_two": 900, "veg_only": false, "lat": 15.5920, "lon": 73.7640, "notes": "Has vegetarian thali, no peanuts in the fish curry", "source": "sample", "status": "proposed"}
]
```
- `place.category`: `sight`, `beach`, `market`, `temple`, `nature`, `activity`, `food_walk`, `other`. `place.price` is per person in rupees (0 if free). `place.day` may be null until scheduled.
- `restaurant.meal`: `breakfast`, `lunch`, `dinner`, `snack`. `price_for_two` in rupees. `restaurant.day` and `date`/`time` may be null until scheduled.
- `status` for both: `proposed`, `selected`, `rejected`. `source`: `live` or `sample` (sample data must be labelled "Sample" in the UI).
- Family needs from household memory (allergies, diet such as pure vegetarian, step-free access) must be used when proposing places and restaurants, and shown in `notes` ("Pure veg options", "Step-free") and in `plan.preferences`.

## Itinerary items get structure

`plan.itinerary[]` items add optional `kind` (`travel`, `stay`, `place`, `food`, `other`), `ref` (the id of the flight, hotel, place or restaurant it comes from, or null) and `cost` (rupees for the whole group, or null). The day-by-day timeline interleaves travel, places and meals in time order, so one glance at "Day 2" shows what we do, where we eat and what that day costs.

## Costs are derived and categorised

`plan.costs[]` lines get `category`: `flights`, `stay`, `food`, `activities`, `local`, `other`. The backend also returns a derived object (never written by the model, recomputed on every change):

```json
"cost_summary": {
  "total": 61400, "per_person": 15350, "travellers": 4, "currency": "INR",
  "by_category": {"flights": 16800, "stay": 26000, "food": 9600, "activities": 4000, "local": 5000, "other": 0},
  "by_day": [{"day": 1, "date": "2026-12-26", "amount": 14200}],
  "budget": 80000, "remaining": 18600, "over_budget": false
}
```
Estimates come from: selected (or, if none selected, the cheapest proposed) flight x travellers, selected hotel x nights x rooms, selected restaurants (price_for_two x travellers / 2), selected places (price x travellers), and explicit `costs` lines (local transport and so on). Anything not yet chosen is shown as an estimate and flagged `"estimate": true` per line in `by_category` detail if useful; at minimum the UI shows "estimate" until things are selected or booked.

## New planner tools (backend)

`search_places(city, interests?)` and `search_restaurants(city, meal?, budget_for_two?, veg_only?)` backed by built-in curated sample data for Goa, Mumbai, Delhi, Jaipur, Kochi/Kerala, Hyderabad, Chennai, Bengaluru, Manali, Ooty, Udaipur (at least 6 places and 6 restaurants for each of the first five, fewer elsewhere) with real coordinates and honest `source: "sample"`; `select_place`, `select_restaurant`, `schedule_item(ref, day, time)`, `add_itinerary_item` (as before). The planner should proactively fill a sensible first draft once destination, dates and travellers are known: flights, hotel, 2-3 places a day, a lunch and a dinner a day, and costs, then refine as people discuss.

## Desktop layout (>= 1024px): the plan is the star, on the LEFT

- **Left, about 62% width: the PLAN BOARD**, which scrolls on its own. Order: trip summary + cost summary strip (total, per person, budget bar) at the top; pending approval; day-by-day itinerary (the main thing: Day 1, Day 2... each with places, meals and the day's cost); places to visit; where to eat; flights; hotels; map (sticky, always visible beside the itinerary on very wide screens, otherwise inside the board); decisions; open questions; checklist; bookings.
- **Right, about 38%: the DISCUSSION**: video strip on top, conversation below it with the message box, Ask Aangan and Summon (voice) at the bottom.
- Phone and tablet (< 1024px): unchanged: video strip, then Plan | Chat tabs.
- Cost summary strip: total and per person, a bar against the budget (calm when under, clear "over by 4,200" when over), and a category breakdown with small bars (flights, stay, food, activities, local).

## Planning-first desktop refinement

This supersedes the 62/38 desktop split above; the room API is unchanged.

- At >= 1024px, the plan gets all space outside a compact 320px companion rail. The rail keeps participants, camera/mic controls, the panda, unresolved questions, voice controls and a quick-message composer visible. Conversation history starts collapsed; an Expand / Collapse conversation button shows unread messages and widens the rail when expanded. A collapsed transcript never marks new messages read. Opening it preserves the draft and transcript scroll behavior.
- The trip summary keeps dates, travellers and family needs visible. The desktop budget is a compact strip (about 90px on a wide screen); total, per person, estimate/demo status, remaining budget and over-budget warnings are never hidden. Category bars are behind the keyboard-accessible Breakdown toggle. Mobile keeps the expanded breakdown.
- Pending approvals remain above the itinerary, with all amounts, booking details, permission checks and demo disclaimers intact. Open questions sit beside the plan in the desktop companion rail, rather than pushing the itinerary down.
- The main canvas is the itinerary beside a sticky map when the board has enough width. Desktop starts on Day 1; day buttons and All days filter the itinerary and schematic map lines together. Changed days show a brief update dot without switching away from the day being read. Phones keep all days and the Plan / Chat tabs.
- The map's Expand button opens a near-fullscreen dialog (fullscreen on phones) with the same selected day, live plan updates and legend. Escape or Close returns focus to Expand; the embedded map retains its zoom and position. Wheel zoom and touch panning are enabled in the expanded map, while the embedded map still lets the page scroll. Expand is disabled until there are map points.
- Map markers have 44px hit areas and distinct SVG pictograms for destination, starting point, stays, sights, food, travel and other stops. Their legend uses the same icons. Hover reveals a place name; keyboard or pointer activation opens its details. Marker labels include the category and name, so colour is not the only way to identify a stop.
- Flights, stays, places, restaurants, decisions, extra costs, checklist and bookings sit in an Options, decisions & trip details disclosure, collapsed initially on desktop and open on mobile. Counts and an Updated badge make new options discoverable without opening the section automatically.
- A live update line names changed sections. New or edited itinerary items briefly draw their connecting line; map lines connect finite coordinates in time order **within each day**, never between separate days. These are labelled as planned stop order, **not driving directions**. Only changed or newly selected routes animate; ordinary room polls do not replay them. Existing history does not animate on load. Reduced-motion preferences remove drawing, node and budget-bar animations.

Focused route tests (from `frontend`, Node with TypeScript stripping): `node --test --experimental-strip-types scripts/map-routes.test.mjs`.
