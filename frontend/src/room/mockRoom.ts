/*
 * Development-only mock of the Family Room API (docs/ROOM_CONTRACT.md). Used only when `import.meta.env.DEV` and the address has `?mock=1`
 * (src/api.ts routes every /rooms request here). It keeps rooms in memory and plays a scripted Goa-trip plan:
 *
 *   message 1 -> goal, destination, dates, travellers and budget, then two flights
 *   message 2 -> hotels, 7 places, 7 restaurants, a 5 day itinerary, costs, a decision, an open question and a checklist
 *   message 3 -> a pending approval to book the morning flight (and a cost that pushes the plan over budget)
 * plan.cost_summary is recomputed on every change from what is selected, as in Addendum 1.
 *
 * Later messages get a short reply when addressed to Aangan (or sent with `ask`). Approve books a demo booking, as the contract says.
 * In the browser console, `__mockRoom.runAll()` plays every step at once, `__mockRoom.reset()` empties the plan.
 */
import { ApiError } from '../api'
import type { Booking, Participant, Plan, Room, RoomMessage } from '../types'
import { buildItinerary, FLIGHTS, HOTELS, PLACES, RESTAURANTS, summarise } from './mockPlanData'

const emptyPlan = (): Plan => ({
  goal: '',
  destination: null,
  origin: null,
  dates: null,
  travelers: [],
  budget: null,
  preferences: [],
  flights: [],
  hotels: [],
  itinerary: [],
  places: [],
  restaurants: [],
  costs: [],
  cost_summary: summarise(null),
  decisions: [],
  open_questions: [],
  checklist: [],
})

interface Mock {
  room: Room
  step: number
  timers: number[]
  nextPid: number
  nextUid: number
  nextMsg: number
}

const rooms = new Map<string, Mock>()
const sleep = (ms: number) => new Promise<void>((r) => window.setTimeout(r, ms))
const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v)) as T
const hhmm = () => {
  const d = new Date()
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

const FRIENDLY: Record<string, string> = { priya: 'Priya', rahul: 'Rahul', aarav: 'Aarav', dadi: 'Dadi' }

function makeRoom(id: string, title: string, hostMember: string | null): Mock {
  const host: Participant = {
    id: 'p-1',
    name: hostMember ? (FRIENDLY[hostMember] ?? hostMember) : 'Priya',
    member_id: hostMember ?? 'priya',
    guest: false,
    rtc_uid: 41231,
    joined_at: hhmm(),
    last_seen: hhmm(),
    online: true,
  }
  const guest: Participant = { id: 'p-2', name: 'Meera (guest)', member_id: null, guest: true, rtc_uid: 41232, joined_at: hhmm(), last_seen: hhmm(), online: true }
  const rahul: Participant = { id: 'p-3', name: 'Rahul', member_id: 'rahul', guest: false, rtc_uid: 41233, joined_at: hhmm(), last_seen: '00:00', online: false }
  const dadi: Participant = { id: 'p-4', name: 'Dadi', member_id: 'dadi', guest: false, rtc_uid: 41234, joined_at: hhmm(), last_seen: '00:00', online: false }
  const room: Room = {
    id,
    version: 1,
    title,
    host_participant_id: host.id,
    created_at: hhmm(),
    participants: [host, guest, rahul, dadi],
    messages: [
      { id: 1, kind: 'user', participant_id: 'p-2', name: guest.name, text: 'Namaste! I opened the link. What are we planning?', ts: hhmm(), lang: 'en' },
      { id: 2, kind: 'user', participant_id: 'p-2', name: guest.name, text: 'చలికాలంలో ప్రయాణం బాగుంటుంది (a winter trip sounds lovely).', ts: hhmm(), lang: 'te' },
    ],
    plan: emptyPlan(),
    pending_approval: null,
    bookings: [],
    agent: { live: false, voice_session: null },
  }
  return { room, step: 0, timers: [], nextPid: 5, nextUid: 41235, nextMsg: 3 }
}

function getMock(id: string): Mock {
  let m = rooms.get(id)
  if (!m) {
    m = makeRoom(id, 'Goa trip', null)
    rooms.set(id, m)
  }
  return m
}

const bump = (m: Mock) => {
  m.room.plan.cost_summary = summarise(m.room.plan)
  m.room.version += 1
}

function push(m: Mock, msg: Omit<RoomMessage, 'id' | 'ts' | 'lang'> & { lang?: string }) {
  m.room.messages.push({ id: m.nextMsg++, ts: hhmm(), lang: 'en', ...msg })
}

const system = (m: Mock, text: string) => push(m, { kind: 'system', participant_id: null, name: '', text })

/** Run `fn` after `ms`, as the background planner would, and bump the version once it has changed something. */
function later(m: Mock, ms: number, fn: () => void) {
  m.timers.push(
    window.setTimeout(() => {
      fn()
      bump(m)
    }, ms),
  )
}

/** The scripted planner. Each step is one burst of visible changes, with the system line the contract describes. */
function runStep(m: Mock, step: number) {
  const p = m.room.plan
  const n = () => Math.max(1, p.travelers.length)
  if (step === 0) {
    later(m, 700, () => {
      p.goal = 'Family trip to Goa'
      p.destination = { name: 'Goa', lat: 15.2993, lon: 74.124 }
      p.origin = { name: 'Bengaluru', lat: 12.9716, lon: 77.5946 }
      p.dates = { start: '2026-12-26', end: '2026-12-30' }
      p.travelers = m.room.participants.slice(0, 4).map((x) => x.id)
      p.budget = { total: 80000, currency: 'INR' }
      p.preferences = ['Dadi needs step-free access', 'Aarav: no peanuts', 'Pure veg options for Dadi']
      system(m, 'Aangan started the plan: Goa, 26 to 30 Dec, 80,000 budget')
    })
    later(m, 2200, () => {
      p.flights = clone(FLIGHTS)
      system(m, 'Aangan added 2 flight options')
    })
  } else if (step === 1) {
    later(m, 700, () => {
      p.hotels = clone(HOTELS)
      system(m, 'Aangan added 2 hotel options')
    })
    later(m, 1700, () => {
      p.places = clone(PLACES).map((x) => ({ ...x, status: 'proposed' as const }))
      p.restaurants = clone(RESTAURANTS).map((x) => ({ ...x, status: 'proposed' as const }))
      system(m, 'Aangan added 7 places and 7 restaurants that suit the family')
    })
    later(m, 2900, () => {
      p.itinerary = buildItinerary(n())
      p.hotels[0].status = 'selected'
      p.places = clone(PLACES)
      p.restaurants = clone(RESTAURANTS)
      p.costs = [{ label: 'Taxis and local travel', amount: 9000, status: 'estimate', category: 'local' }]
      system(m, 'Aangan drafted a 5 day itinerary')
    })
    later(m, 3800, () => {
      p.decisions = [{ id: 'd-1', text: 'Fly on the 26th morning', by: m.room.participants.slice(0, 2).map((x) => x.id), ts: hhmm() }]
      p.open_questions = [{ id: 'q-1', text: 'How many rooms do we need?', asked_by: 'Aangan', ts: hhmm(), resolved: false }]
      p.checklist = [
        { id: 'c-1', text: "Check Dadi's medicine stock before travel", done: false, owner: null },
        { id: 'c-2', text: 'Print the hotel booking', done: true, owner: m.room.host_participant_id },
      ]
      system(m, 'Aangan updated decisions and the checklist')
    })
  } else if (step === 2) {
    later(m, 800, () => {
      p.flights[0].status = 'selected'
      if (p.flights[1]) p.flights[1].status = 'rejected'
      p.costs = [...p.costs, { label: 'Water sports and a boat trip', amount: 14000, status: 'estimate', category: 'activities' }]
      m.room.pending_approval = {
        id: 'a-1',
        kind: 'booking',
        title: 'Book IndiGo 6E-512 for 4 people',
        summary: '4 seats BLR to GOI on 26 Dec 07:10, 16,800 total. Demo booking: no real money moves.',
        amount: 16800,
        items: ['f-1'],
        needs: 'host',
        approvals: [],
        status: 'waiting',
      }
      push(m, { kind: 'agent', participant_id: null, name: 'Aangan', text: 'I can book the 07:10 IndiGo flight for all four of you. It needs the host to approve it. With water sports added, the plan is now a little over budget.' })
    })
  }
}

/** Plays every remaining step, spaced out so each one finds what the one before it added (about 8 seconds in all). */
function runAll(m: Mock) {
  const gap = [0, 3000, 8000]
  const from = m.step
  for (let step = from; step < 3; step++) window.setTimeout(() => runStep(m, step), gap[step] - gap[from])
  m.step = 3
}

const addressed = (text: string, ask: boolean) => ask || /aangan/i.test(text) || /\?\s*$/.test(text)

function onHumanMessage(m: Mock, text: string, ask: boolean) {
  if (m.step < 3) {
    runStep(m, m.step)
    m.step++
  } else {
    later(m, 700, () => system(m, 'Aangan noted that'))
  }
  if (addressed(text, ask)) {
    later(m, 500, () => push(m, { kind: 'agent', participant_id: null, name: 'Aangan', text: 'Got it. I am updating the plan and will tell you if I need a decision.' }))
  }
}

type Body = Record<string, unknown>
const str = (v: unknown) => (typeof v === 'string' ? v : '')

function needParticipant(m: Mock, id: unknown): Participant {
  const p = m.room.participants.find((x) => x.id === id)
  if (!p) throw new ApiError(404, 'unknown participant', 'unknown participant')
  return p
}

const touch = (p: Participant) => {
  p.last_seen = hhmm()
  p.online = true
}

export async function mockRoomRequest(path: string, body?: unknown): Promise<unknown> {
  await sleep(60 + Math.random() * 60)
  const [pathname, query = ''] = path.split('?')
  const parts = pathname.split('/').filter(Boolean) // ['rooms', id, action?, sub?]
  const b = (body ?? {}) as Body

  if (parts.length === 1 && body !== undefined) {
    const id = `r-mock${Math.random().toString(16).slice(2, 6)}`
    const m = makeRoom(id, str(b.title).trim() || 'Goa trip', typeof b.member_id === 'string' ? b.member_id : null)
    m.room.messages = []
    m.nextMsg = 1
    rooms.set(id, m)
    return clone(m.room)
  }

  const id = decodeURIComponent(parts[1] ?? '')
  const action = parts.slice(2).join('/')
  if (!id) throw new ApiError(404, 'unknown room', 'unknown room')
  if (id === 'missing') throw new ApiError(404, 'unknown room', 'unknown room')
  const m = getMock(id)
  const room = m.room

  if (body === undefined && !action) {
    const since = Number(new URLSearchParams(query).get('since') ?? NaN)
    if (since === room.version) return { id: room.id, version: room.version, unchanged: true }
    return clone(room)
  }

  switch (action) {
    case 'join': {
      if (typeof b.member_id === 'string') {
        const existing = room.participants.find((x) => x.member_id === b.member_id)
        if (existing) {
          touch(existing)
          return { participant: clone(existing), room: clone(room) }
        }
        const p: Participant = { id: `p-${m.nextPid++}`, name: FRIENDLY[b.member_id] ?? b.member_id, member_id: b.member_id, guest: false, rtc_uid: m.nextUid++, joined_at: hhmm(), last_seen: hhmm(), online: true }
        room.participants.push(p)
        bump(m)
        return { participant: clone(p), room: clone(room) }
      }
      const name = str(b.guest_name).trim()
      if (!name) throw new ApiError(422, 'A name is needed', 'A name is needed')
      const p: Participant = { id: `p-${m.nextPid++}`, name: `${name} (guest)`, member_id: null, guest: true, rtc_uid: m.nextUid++, joined_at: hhmm(), last_seen: hhmm(), online: true }
      room.participants.push(p)
      bump(m)
      return { participant: clone(p), room: clone(room) }
    }
    case 'heartbeat': {
      touch(needParticipant(m, b.participant_id))
      return { ok: true }
    }
    case 'message': {
      const p = needParticipant(m, b.participant_id)
      touch(p)
      const text = str(b.text).trim()
      push(m, { kind: 'user', participant_id: p.id, name: p.name, text })
      bump(m)
      onHumanMessage(m, text, b.ask === true)
      return clone(room)
    }
    case 'approve': {
      const p = needParticipant(m, b.participant_id)
      const pending = room.pending_approval
      if (!pending) return clone(room)
      if (pending.needs === 'host' && p.id !== room.host_participant_id) throw new ApiError(403, 'Only the host can approve this', 'Only the host can approve this')
      if (b.approve === true) {
        const flight = room.plan.flights.find((f) => pending.items.includes(f.id))
        if (flight) flight.status = 'booked'
        const booking: Booking = {
          id: `b-${room.bookings.length + 1}`,
          kind: 'flight',
          ref: 'DEMO-4F2K9',
          title: flight ? `${flight.airline} ${flight.number}, 26 Dec ${flight.dep}, 4 travellers` : pending.title,
          amount: pending.amount,
          demo: true,
          ts: hhmm(),
        }
        room.bookings.push(booking)
        system(m, `${p.name} approved: ${booking.title} booked (demo)`)
      } else {
        system(m, `${p.name} declined: ${pending.title}`)
      }
      room.pending_approval = null
      bump(m)
      return clone(room)
    }
    case 'rtc': {
      const p = needParticipant(m, b.participant_id)
      // app_id "mock" tells the client not to join a real channel.
      return { app_id: 'mock', channel: `room-${room.id}`, token: 'mock', uid: p.rtc_uid, rtm_token: 'mock', rtm_user_id: String(p.rtc_uid) }
    }
    case 'agent/start': {
      needParticipant(m, b.participant_id)
      room.agent = { live: true, voice_session: { agent_uid: '123456' } }
      const greeting = 'Namaste, I am here. Tell me what you would like to plan.'
      push(m, { kind: 'agent', participant_id: null, name: 'Aangan', text: greeting })
      bump(m)
      return { agent_id: 'mock-agent', agent_uid: '123456', greeting }
    }
    case 'agent/stop': {
      room.agent = { live: false, voice_session: null }
      bump(m)
      return { stopped: true }
    }
    case 'reset-plan': {
      m.timers.forEach((t) => window.clearTimeout(t))
      m.timers = []
      room.plan = emptyPlan()
      room.pending_approval = null
      room.bookings = []
      m.step = 0
      bump(m)
      return clone(room)
    }
  }
  throw new ApiError(404, 'unknown route', 'unknown route')
}

if (import.meta.env.DEV) {
  ;(window as unknown as { __mockRoom: unknown }).__mockRoom = {
    runAll: (id = 'demo') => runAll(getMock(id)),
    reset: (id = 'demo') => void mockRoomRequest(`/rooms/${id}/reset-plan`, {}),
    rooms,
  }
}
