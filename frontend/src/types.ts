export type MemberKind = 'adult' | 'child' | 'senior'
export type Stage = 'before' | 'during' | 'action' | 'after'

export interface Member {
  id: string
  name: string
  relation: string
  age: number
  kind: MemberKind
  language: string
  locale: string
  color: string
  about: string
  voice_id?: string | null
  gender?: 'female' | 'male' | string
}

export type MemberLanguage = 'English' | 'Hindi' | 'Hinglish' | 'Telugu' | 'Kannada'
export type MemberGender = 'female' | 'male'

/** What the household tools take to add or change a person. */
export interface MemberArgs {
  name: string
  relation: string
  age: number
  kind?: MemberKind
  language?: MemberLanguage
  gender?: MemberGender
  diet?: string[]
  allergies?: string[]
  notes?: string
}

/** The outcome of a household tool call made without a toast, for forms that show their own result. */
export interface ToolOutcome<T = Record<string, unknown>> {
  ok: boolean
  result: T
  /** Plain-language reason when ok is false. */
  error?: string
}

export interface MemoryFact {
  id: string
  about: string
  fact: string
  tags: string[]
}

export interface CalendarEvent {
  id: string
  title: string
  member_ids: string[]
  date: string
  start: string
  end: string
  location: string
  kind: string
  source: string
}

export interface ToolEvent {
  id: number
  stage: Stage
  agent: string
  tool: string
  args: Record<string, unknown>
  status: 'ok' | 'error'
  result: Record<string, unknown>
  ms: number
  ts: string
}

export interface Notification {
  id: number
  to: string[]
  kind: string
  agent: string
  text: string
  channel: string
  mode: 'live' | 'in_app'
  status: 'sent' | 'in_app' | 'failed'
  at: string
  date: string
}

export interface TranscriptEntry {
  role: 'user' | 'agent'
  member_id: string
  agent: string | null
  text: string
  ts: string
}

export interface AgentInfo {
  name: string
  title: string
  triggers: { name: string; label: string }[]
}

export interface Mark {
  id: string
  subject: string
  score: number
  max: number
  date: string
  exam: string
}

export interface Homework {
  id: string
  subject: string
  task: string
  due: string
  done: boolean
}

export interface SchoolKid {
  grade: string
  status: string
  arrived_at: string | null
  last_location: string
  marks: Mark[]
  homework: Homework[]
}

export interface Medicine {
  id: string
  name: string
  dose: string
  times: string[]
  stock_days: number
  taken: Record<string, unknown>
}

export interface CareSenior {
  meds: Medicine[]
  checkin_times: string[]
  last_checkin: unknown
  doctor: { name: string; clinic: string; next_appointment: { date: string; time: string } | null }
  emergency_contacts: string[]
}

export interface Domains {
  school?: { school?: { name: string; start: string; bus_pickup: string }; kids?: Record<string, SchoolKid> }
  care?: { seniors?: Record<string, CareSenior> }
  travel?: { trips?: Record<string, unknown>[] }
  dining?: { reservations?: Record<string, unknown>[] }
  [agent: string]: unknown
}

export interface Snapshot {
  now: { date: string; time: string }
  persona: string
  stage: Stage
  chaos: boolean
  /** `exists` is false until the first person is added; `demo` is true while the built-in example family is loaded. */
  household?: { exists: boolean; demo: boolean }
  members: Member[]
  memory: MemoryFact[]
  calendar: CalendarEvent[]
  domains: Domains
  pending: ({ agent?: string } & Record<string, unknown>) | null
  events: ToolEvent[]
  notifications: Notification[]
  transcript: TranscriptEntry[]
  agents: AgentInfo[]
}

export interface ServiceStatus {
  configured: boolean
  missing: string[]
}

export interface AppConfig {
  services: { agora: ServiceStatus; murf: ServiceStatus; voice: ServiceStatus; chat: ServiceStatus; llm: ServiceStatus }
  brain: 'llm' | 'rules'
  llm?: { provider: 'gateway' | 'openai' | 'anthropic'; model: string } | null
  voices: Record<string, { name: string; locale: string; gender: string; language: string }>
  tts: { vendor: string; model: string }
  llm_url: string | null
  language_mode?: 'multi' | 'english' | 'native'
  languages?: { code: string; name: string; native: string }[]
}

export interface ToolSpec {
  agent: string
  name: string
  description: string
  parameters: { type: 'object'; properties?: Record<string, { type?: string; description?: string; enum?: string[]; items?: unknown }>; required?: string[] }
}

export interface VoiceSession {
  app_id: string
  channel: string
  /** RTC token for the browser. Today the backend mints one combined RTC+RTM token and returns it in both fields. */
  token: string
  uid: number
  rtm_token?: string
  /** RTM login identity; must equal the identity the RTM token was minted for (String(uid)). */
  rtm_user_id?: string
  agent_id: string
  /** The agent's RTC uid as a string, used to tell its audio, presence and transcript turns apart. */
  agent_uid?: string
  greeting: string
  member_id: string
  status: string
  voice?: { name: string; voice_id?: string; locale: string; gender: string; language: string }
  language_mode?: 'multi' | 'english' | 'native'
}

/* ---------------------------------------------------------------------------------------------------------------------------------
 * Family Room (see docs/ROOM_CONTRACT.md). Field names follow the contract exactly.
 * ------------------------------------------------------------------------------------------------------------------------------ */

export interface Participant {
  id: string
  name: string
  member_id: string | null
  guest: boolean
  rtc_uid: number
  joined_at: string
  last_seen: string
  online: boolean
}

export interface RoomMessage {
  id: number
  kind: 'user' | 'agent' | 'system'
  participant_id: string | null
  name: string
  text: string
  ts: string
  lang: string
}

export interface Place {
  name: string
  lat: number
  lon: number
}

export type PlanItemStatus = 'proposed' | 'selected' | 'booked' | 'rejected'
export type PlanSource = 'live' | 'sample'

export interface Flight {
  id: string
  airline: string
  number: string
  from: string
  to: string
  date: string
  dep: string
  arr: string
  price: number
  per: 'person' | 'total' | string
  stops: number
  source: PlanSource
  link: string | null
  status: PlanItemStatus
}

export interface Hotel {
  id: string
  name: string
  area: string
  price_per_night: number
  rating: number
  lat: number
  lon: number
  step_free: boolean
  source: PlanSource
  status: PlanItemStatus
}

export interface ItineraryItem {
  id: string
  day: number
  date: string
  time: string
  title: string
  place: string
  lat: number
  lon: number
  notes: string
  /** Addendum 1: what kind of entry it is, the flight, hotel, place or restaurant it comes from, and its cost for the whole group. */
  kind?: 'travel' | 'stay' | 'place' | 'food' | 'other' | null
  ref?: string | null
  cost?: number | null
}

export type CostCategory = 'flights' | 'stay' | 'food' | 'activities' | 'local' | 'other'

export interface Cost {
  label: string
  amount: number
  status: 'estimate' | 'confirmed' | string
  category?: CostCategory | null
}

export type PlaceCategory = 'sight' | 'beach' | 'market' | 'temple' | 'nature' | 'activity' | 'food_walk' | 'other'

/** A place to visit (Addendum 1). Not to be confused with `Place`, a named point on the map. */
export interface PlaceToVisit {
  id: string
  name: string
  area: string
  category: PlaceCategory | string
  lat: number
  lon: number
  duration_min: number | null
  /** Rupees per person; 0 when free. */
  price: number
  per: 'person' | 'total' | string
  day: number | null
  notes: string
  source: PlanSource
  status: PlanItemStatus
}

export type Meal = 'breakfast' | 'lunch' | 'dinner' | 'snack'

export interface Restaurant {
  id: string
  name: string
  cuisine: string
  area: string
  meal: Meal | string
  day: number | null
  date: string | null
  time: string | null
  price_for_two: number
  veg_only: boolean
  lat: number
  lon: number
  notes: string
  source: PlanSource
  status: PlanItemStatus
}

/** Derived by the backend on every change, never written by the model. */
export interface CostSummary {
  total: number
  per_person: number
  travellers: number
  currency: string
  by_category: Partial<Record<CostCategory, number>>
  by_day: { day: number; date: string; amount: number }[]
  budget: number | null
  remaining: number | null
  over_budget: boolean
}

export interface Decision {
  id: string
  text: string
  by: string[]
  ts: string
}

export interface OpenQuestion {
  id: string
  text: string
  asked_by: string
  ts: string
  resolved: boolean
}

export interface ChecklistItem {
  id: string
  text: string
  done: boolean
  owner: string | null
}

export interface Plan {
  goal: string
  destination: Place | null
  origin: Place | null
  dates: { start: string; end: string } | null
  travelers: string[]
  budget: { total: number; currency: string } | null
  preferences: string[]
  flights: Flight[]
  hotels: Hotel[]
  itinerary: ItineraryItem[]
  places: PlaceToVisit[]
  restaurants: Restaurant[]
  costs: Cost[]
  cost_summary: CostSummary
  decisions: Decision[]
  open_questions: OpenQuestion[]
  checklist: ChecklistItem[]
}

export interface PendingApproval {
  id: string
  kind: 'booking' | 'other'
  title: string
  summary: string
  amount: number
  items: string[]
  needs: 'host' | 'anyone'
  approvals: string[]
  status: 'waiting' | 'approved' | 'declined'
}

export interface Booking {
  id: string
  kind: string
  ref: string
  title: string
  amount: number
  demo: boolean
  ts: string
}

export interface Room {
  id: string
  version: number
  title: string
  host_participant_id: string
  created_at: string
  participants: Participant[]
  messages: RoomMessage[]
  plan: Plan
  pending_approval: PendingApproval | null
  bookings: Booking[]
  agent: { live: boolean; voice_session: ({ agent_uid?: string | number } & Record<string, unknown>) | null }
}

/** What GET /rooms/{id}?since=N returns when nothing changed. */
export interface RoomUnchanged {
  id: string
  version: number
  unchanged: true
}

export interface RoomRtcSession {
  app_id: string
  channel: string
  token: string
  uid: number
  rtm_token?: string
  rtm_user_id?: string
}

export interface RoomAgentSession {
  agent_id: string
  agent_uid: string
  greeting: string
}
