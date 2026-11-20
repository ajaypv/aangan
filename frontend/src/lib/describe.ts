import { addDays, dayLabel, memberOf } from '@/lib/format'
import type { Snapshot, ToolEvent } from '@/types'

/**
 * Turns a raw tool call into a short human sentence ("Booked a table for 4 at Udupi Garden"). Every tool of every agent has a sentence;
 * unknown tools fall back to a readable version of their name, so a new tool never shows up as raw JSON.
 *
 *   action  - something Aangan changed or sent (counts as "did a thing")
 *   lookup  - something Aangan only looked up (shown quietly)
 *   context - what Aangan remembered before answering (the "Before" stage)
 *   hidden  - plumbing the user never needs to see
 */
export type DescribedKind = 'action' | 'lookup' | 'context' | 'hidden'

export interface Described {
  id: number
  agent: string
  tool: string
  /** The time the call ran (HH:MM:SS). */
  ts: string
  kind: DescribedKind
  ok: boolean
  /** One sentence, no trailing full stop. On failure this says what could not be done. */
  text: string
  /** Why it failed, in plain words. Only set when ok is false. */
  reason?: string
}

type Core = Pick<Described, 'kind' | 'ok' | 'text' | 'reason'>

type Bag = Record<string, unknown>

const str = (v: unknown): string => (typeof v === 'string' ? v : typeof v === 'number' ? String(v) : '')
const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : typeof v === 'string' && v.trim() !== '' && Number.isFinite(Number(v)) ? Number(v) : null)
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : [])
const bag = (v: unknown): Bag => (typeof v === 'object' && v !== null && !Array.isArray(v) ? (v as Bag) : {})
const words = (s: string) => s.replace(/[_-]+/g, ' ').trim()
const cap = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s)
const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`

/** 13:00 becomes 1:00 PM. Anything that is not HH:MM is returned unchanged. */
export function time12(hhmm: unknown): string {
  const s = str(hhmm)
  const m = /^(\d{1,2}):(\d{2})/.exec(s)
  if (!m) return s
  const h = Number(m[1])
  return `${h % 12 === 0 ? 12 : h % 12}:${m[2]} ${h < 12 ? 'AM' : 'PM'}`
}

/** Rupees the way a person says them: Rs 1,800 becomes ₹1,800. */
export function rupees(n: unknown): string {
  const v = num(n)
  return v === null ? '' : `₹${Math.round(v).toLocaleString('en-IN')}`
}

const day = (snap: Snapshot, iso: unknown): string => {
  const d = str(iso)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) return ''
  if (d === snap.now.date) return 'today'
  if (d === addDays(snap.now.date, 1)) return 'tomorrow'
  return dayLabel(d)
}
const onDay = (snap: Snapshot, iso: unknown) => {
  const d = day(snap, iso)
  return d ? ` ${d === 'today' || d === 'tomorrow' ? d : `on ${d}`}` : ''
}

const person = (snap: Snapshot, id: unknown): string => {
  const s = str(id)
  if (!s) return 'someone'
  return memberOf(snap, s)?.name ?? cap(s)
}

/** "Priya and Rahul", "Priya, Rahul and Aarav", or "everyone" when it is the whole household. */
function people(snap: Snapshot, ids: unknown): string {
  const list = arr(ids).map(str).filter(Boolean)
  if (list.length === 0) return 'the family'
  if (list.length > 1 && list.length === snap.members.length && snap.members.every((m) => list.includes(m.id))) return 'everyone'
  const names = list.map((id) => person(snap, id))
  return names.length === 1 ? names[0] : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
}

const possessive = (name: string) => (name.endsWith('s') ? `${name}’` : `${name}’s`)

const LOOKUPS = new Set([
  'search_restaurants',
  'find_family_slots',
  'get_schedule',
  'check_conflicts',
  'scan_clashes',
  'search_flights',
  'get_trip',
  'get_child_summary',
  'get_care_summary',
  'recall',
  'family_summary',
  'list_expenses',
  'get_spending_summary',
  'get_budget_status',
  'suggest_savings',
])

/** What could not be done, for the failed version of each tool. */
const COULD_NOT: Record<string, string> = {
  search_restaurants: 'search for restaurants',
  book_table: 'book the table',
  add_calendar_event: 'add the plan to the calendar',
  arrange_pickup: 'book the cab',
  cancel_reservation: 'cancel the reservation',
  notify_family: 'tell the family',
  find_family_slots: 'find a time that works for everyone',
  get_schedule: 'read the schedule',
  check_conflicts: 'check for clashes',
  scan_clashes: 'scan for clashes',
  create_event: 'add the event',
  move_event: 'move the event',
  cancel_event: 'cancel the event',
  send_digest: 'send the digest',
  search_flights: 'search for flights',
  search_transport: 'look at trains, buses and cars',
  set_local_transport: 'set how you get around',
  book_flight: 'book the flight',
  rebook_flight: 'rebook the flight',
  update_cab_pickup: 'move the cab',
  book_cab: 'book the cab',
  add_trip_to_calendar: 'add the flight to the calendar',
  get_trip: 'look up the trip',
  flight_status_webhook: 'record the flight delay',
  record_arrival: 'record the arrival',
  log_marks: 'log the marks',
  get_child_summary: 'check school progress',
  add_homework: 'add the homework',
  complete_homework: 'mark the homework done',
  notify_parents: 'tell the parents',
  log_medicine_taken: 'log the medicine',
  record_checkin: 'log the check-in',
  escalate_missed_checkin: 'alert the family',
  order_refill: 'order the refill',
  book_appointment: 'book the appointment',
  add_medicine: 'add the medicine',
  get_care_summary: 'check on them',
  add_member: 'add the person',
  update_member: 'update the profile',
  remove_member: 'remove the person',
  remember_fact: 'remember that',
  forget_fact: 'forget that',
  recall: 'recall what is known',
  family_summary: 'list the family',
  log_expense: 'log the expense',
  delete_expense: 'delete the expense',
  list_expenses: 'list the expenses',
  get_spending_summary: 'work out the spending',
  set_budget: 'set the budget',
  get_budget_status: 'check the budget',
  suggest_savings: 'look for savings',
}

/** A reason a person can read: no status codes, no stack of jargon, ends with a full stop. */
export function plainReason(raw: unknown): string {
  let s = str(raw).trim() || 'Something went wrong'
  if (/seat hold/i.test(s) && /expired/i.test(s)) return 'The airline released the seat hold.'
  if (/just taken|slot .*taken/i.test(s)) return 'That table was just taken.'
  if (/failed to fetch|network|cannot reach/i.test(s)) return 'Aangan could not reach the service.'
  s = s.replace(/\s*\((?:HTTP|status|code)[^)]*\)/gi, '').replace(/\s*\bHTTP\s*\d{3}\b/gi, '').trim()
  s = cap(s)
  return /[.!?]$/.test(s) ? s : `${s}.`
}

function failure(e: ToolEvent): Core {
  const what = COULD_NOT[e.tool] ?? `run ${words(e.tool)}`
  return { kind: LOOKUPS.has(e.tool) ? 'lookup' : 'action', ok: false, text: `Could not ${what}`, reason: plainReason(e.result.error) }
}

const ok = (kind: DescribedKind, text: string): Core => ({ kind, ok: true, text })

/** The channel a family message went out on, in words. */
function channelPhrase(r: Bag): string {
  const status = str(r.status)
  if (status === 'sent') return 'on Agora Chat'
  if (status === 'failed') return 'on Agora Chat'
  return 'in the app'
}

export function describeEvent(e: ToolEvent, snap: Snapshot): Described {
  return { id: e.id, agent: e.agent, tool: e.tool, ts: e.ts, ...describeCore(e, snap) }
}

function describeCore(e: ToolEvent, snap: Snapshot): Core {
  if (e.agent === 'orchestrator') {
    if (e.tool === 'load_member_context') {
      const facts = arr(e.result.facts).length + arr(e.result.family_facts).length
      const who = str(e.result.speaker) || 'you'
      return ok('context', facts > 0 ? `Recalled ${plural(facts, 'thing')} about ${who} and the family` : `Checked what it knows about ${who}`)
    }
    return { kind: 'hidden', ok: e.status === 'ok', text: cap(words(e.tool)) }
  }
  if (e.status === 'error') return failure(e)

  const a = e.args
  const r = e.result
  const kind: DescribedKind = LOOKUPS.has(e.tool) ? 'lookup' : 'action'

  switch (e.tool) {
    // ---- dining
    case 'search_restaurants': {
      const matches = arr(r.matches)
      const best = str(bag(matches[0]).name)
      if (matches.length) return ok(kind, `Found ${plural(matches.length, 'restaurant')} that ${matches.length === 1 ? 'suits' : 'suit'} everyone${best ? `, best is ${best}` : ''}`)
      return ok(kind, 'Looked for a restaurant, but none fit every need')
    }
    case 'book_table': {
      const size = num(r.party_size) ?? num(a.party_size)
      return ok(kind, `Booked a table${size ? ` for ${size}` : ''} at ${str(r.restaurant) || 'the restaurant'}${onDay(snap, r.date ?? a.date)}${r.time ? ` at ${time12(r.time)}` : ''}`)
    }
    case 'add_calendar_event': {
      const ids = r.attendees ?? a.member_ids
      const who = people(snap, ids)
      const title = str(r.title) || str(a.title) || 'the plan'
      return ok(kind, who === 'everyone' ? `Added “${title}” to everyone’s calendar` : `Added “${title}” to the calendar for ${who}`)
    }
    case 'arrange_pickup':
      return ok(kind, `Booked a cab for ${str(r.for) || person(snap, a.member_id)} at ${time12(r.pickup ?? a.pickup_time)}`)
    case 'cancel_reservation':
      return ok(kind, `Cancelled the reservation${str(r.restaurant) ? ` at ${str(r.restaurant)}` : ''}`)
    case 'notify_family':
    case 'notify_parents': {
      const to = arr(r.to).length ? r.to : (a.member_ids ?? a.to)
      const failed = str(r.status) === 'failed'
      const who = e.tool === 'notify_parents' && !arr(to).length ? 'the parents' : people(snap, to)
      if (failed) return { kind: 'action', ok: false, text: `Could not tell ${who} on Agora Chat`, reason: 'Agora Chat did not accept the message.' }
      return ok(kind, `Told ${who} ${channelPhrase(r)}`)
    }

    // ---- calendar
    case 'find_family_slots': {
      const best = bag(r.best)
      const ids = r.member_ids ?? a.member_ids
      const who = people(snap, ids)
      const verb = who === 'everyone' || arr(ids).length <= 1 ? 'is' : 'are'
      return ok(kind, `Looked for a time when ${who} ${verb} free${onDay(snap, r.date ?? a.date)}${best.start ? `, best is ${time12(best.start)}` : ''}`)
    }
    case 'get_schedule':
      return ok(kind, `Checked ${arr(a.member_ids).length === 1 ? possessive(person(snap, arr(a.member_ids)[0])) : `${possessive(people(snap, a.member_ids))}`} schedule${onDay(snap, r.date ?? a.date)}`)
    case 'check_conflicts':
      return ok(kind, r.has_conflicts ? 'Checked the time and found a clash' : 'Checked the time and found no clash')
    case 'scan_clashes': {
      const n = arr(r.clashes).length + arr(r.heads_up).length
      return ok(kind, n ? `Scanned the week and found ${plural(n, 'thing')} to watch` : 'Scanned the week and found no clashes')
    }
    case 'create_event': {
      const ev = bag(r.event)
      return ok(kind, `Added “${str(ev.title) || str(a.title)}”${onDay(snap, ev.date ?? a.date)}${ev.start || a.start ? ` at ${time12(ev.start ?? a.start)}` : ''}`)
    }
    case 'move_event': {
      const ev = bag(r.event)
      return ok(kind, `Moved “${str(ev.title) || 'the event'}” to ${time12(ev.start ?? a.start)}${onDay(snap, ev.date ?? a.date)}`)
    }
    case 'cancel_event':
      return ok(kind, `Cancelled “${str(bag(r.cancelled).title) || 'the event'}”`)
    case 'send_digest':
      return ok(kind, `Sent the weekly digest to ${people(snap, a.member_ids)}`)

    // ---- travel
    case 'search_flights': {
      const n = arr(r.options).length
      return ok(kind, n ? `Found ${plural(n, 'flight')} from ${str(a.route).replace('->', 'to')}` : `Looked for flights ${str(a.route).replace('->', 'to')} and found none that fit`)
    }
    case 'book_flight':
      return ok(kind, `Booked ${str(r.airline)} ${str(r.flight)} for ${people(snap, r.member_ids ?? a.member_ids)}, ${str(r.route).replace('->', 'to')}${onDay(snap, r.date)}`.replace(/\s+/g, ' '))
    case 'rebook_flight':
      return ok(kind, `Rebooked onto ${str(r.airline)} ${str(r.flight)}, leaving at ${time12(r.dep)}`)
    case 'update_cab_pickup':
      return ok(kind, `Moved the airport cab to ${time12(r.new_pickup)}`)
    case 'book_cab':
      return ok(kind, `Booked a cab for ${time12(r.pickup)}${str(r.to) ? ` to ${str(r.to)}` : ''}`)
    case 'add_trip_to_calendar':
      return ok(kind, 'Added the flight to the calendar')
    case 'get_trip':
      return ok(kind, 'Looked up the trip details')
    case 'flight_status_webhook': {
      const delay = num(r.delay_min) ?? num(a.delay_min)
      return ok(kind, delay ? `Recorded a flight delay of ${delay >= 60 ? `${Math.round((delay / 60) * 10) / 10} hours` : `${delay} minutes`}` : 'Recorded a flight status change')
    }

    // ---- school
    case 'record_arrival': {
      const who = str(r.name) || person(snap, a.member_id)
      return ok(kind, `${who} reached school at ${time12(r.arrived_at)}${r.on_time === true ? ', on time' : r.on_time === false ? ', after the bell' : ''}`)
    }
    case 'log_marks': {
      const mark = bag(r.mark)
      return ok(kind, `Logged ${possessive(str(r.name) || person(snap, a.member_id))} ${str(mark.subject) || str(a.subject)} marks: ${str(mark.score ?? a.score)} out of ${str(mark.max ?? a.max)}`)
    }
    case 'get_child_summary':
      return ok(kind, `Checked ${possessive(str(r.name) || person(snap, a.member_id))} school progress`)
    case 'add_homework':
      return ok(kind, `Added ${str(a.subject)} homework for ${person(snap, a.member_id)}`.replace('  ', ' '))
    case 'complete_homework': {
      const hw = bag(r.homework)
      return ok(kind, `Marked ${possessive(str(r.name) || person(snap, a.member_id))} ${str(hw.subject)} homework done`.replace('  ', ' '))
    }

    // ---- care
    case 'log_medicine_taken': {
      const meds = arr(r.logged).map((m) => str(bag(m).med)).filter(Boolean)
      const who = person(snap, a.member_id ?? r.member_id)
      return ok(kind, meds.length ? `Logged ${possessive(who)} medicine: ${[...new Set(meds)].join(' and ')}` : `Checked ${possessive(who)} medicine, nothing was due`)
    }
    case 'record_checkin': {
      const mood = str(a.mood)
      return ok(kind, `Logged ${possessive(person(snap, a.member_id))} check-in${mood ? `, feeling ${words(mood)}` : ''}`)
    }
    case 'escalate_missed_checkin':
      return ok(kind, `Alerted ${people(snap, r.notified ?? r.to)} that ${person(snap, a.member_id)} missed a check-in`)
    case 'order_refill': {
      const arrives = day(snap, str(r.eta).split(' ')[0])
      return ok(kind, `Ordered a refill of ${str(r.med) || str(a.med_name)} for ${person(snap, a.member_id ?? r.member_id)}${arrives ? `, arriving ${arrives}` : ''}`)
    }
    case 'book_appointment':
      return ok(kind, `Booked ${str(r.doctor) || 'the doctor'} for ${person(snap, a.member_id ?? r.member_id)}${onDay(snap, r.date ?? a.date)} at ${time12(r.time ?? a.time)}`)
    case 'add_medicine':
      return ok(kind, `Added ${str(a.name) || str(a.med_name) || 'a medicine'} to ${possessive(person(snap, a.member_id))} list`)
    case 'get_care_summary':
      return ok(kind, `Checked on ${person(snap, a.member_id ?? r.member_id)}: ${num(r.taken) ?? 0} of ${num(r.total) ?? 0} doses taken`)

    // ---- household
    case 'add_member':
      return ok(kind, `Added ${str(bag(r.member).name) || str(a.name)} to the family`)
    case 'update_member':
      return ok(kind, `Updated ${possessive(str(bag(r.member).name) || person(snap, a.member_id))} profile`)
    case 'remove_member':
      return ok(kind, `Removed ${str(r.name) || person(snap, a.member_id)} from the family`)
    case 'remember_fact': {
      const fact = str(bag(r.fact).fact) || str(a.fact)
      return ok(kind, r.duplicate ? `Already knew: ${fact}` : `Remembered: ${fact}${str(a.about) && str(a.about) !== 'family' ? ` (${person(snap, a.about)})` : ''}`)
    }
    case 'forget_fact':
      return ok(kind, 'Forgot a remembered fact')
    case 'recall':
      return ok(kind, `Recalled what the family knows about ${str(r.name) || (str(a.about) === 'family' ? 'the family' : person(snap, a.about))}`)
    case 'family_summary':
      return ok(kind, 'Listed everyone in the family')

    // ---- money
    case 'log_expense': {
      const ex = bag(r.expense)
      return ok(kind, `Logged ${rupees(ex.amount ?? a.amount)} for ${str(ex.category) || str(a.category) || 'spending'}`)
    }
    case 'delete_expense':
      return ok(kind, 'Deleted an expense')
    case 'list_expenses':
      return ok(kind, 'Looked through the recent expenses')
    case 'get_spending_summary': {
      const total = rupees(r.total)
      return ok(kind, `Added up spending ${str(r.label) || str(a.period) || ''}${total ? `: ${total}` : ''}`.replace('  ', ' ').trim())
    }
    case 'set_budget':
      return ok(kind, `Set the ${str(a.category) === 'total' ? 'overall' : str(a.category)} budget to ${rupees(a.amount)} a month`)
    case 'get_budget_status':
      return ok(kind, 'Checked the budget')
    case 'suggest_savings': {
      const save = rupees(r.potential_savings)
      return ok(kind, save && num(r.potential_savings) ? `Looked for savings and found about ${save} a month` : 'Looked for ways to save')
    }
  }
  return ok(kind, cap(words(e.tool)))
}

export interface Summary {
  actions: Described[]
  lookups: Described[]
  context: Described[]
  failed: Described[]
  /** "Aangan did 3 things", "Aangan checked 2 things", or "" when there is nothing to show. */
  line: string
}

/** Groups a reply's tool calls and builds the collapsed line shown under it. */
export function summarize(events: ToolEvent[], snap: Snapshot): Summary {
  const all = events.map((e) => describeEvent(e, snap))
  const visible = all.filter((d) => d.kind !== 'hidden')
  const actions = visible.filter((d) => d.kind === 'action')
  const lookups = visible.filter((d) => d.kind === 'lookup')
  const context = visible.filter((d) => d.kind === 'context')
  const failed = visible.filter((d) => !d.ok)
  const done = actions.filter((d) => d.ok).length
  let line = ''
  if (done > 0) line = `Aangan did ${plural(done, 'thing')}`
  else if (lookups.length > 0) line = `Aangan checked ${plural(lookups.length, 'thing')}`
  else if (failed.length > 0) line = 'Aangan tried but could not finish'
  if (line && failed.length > 0 && done > 0) line += `, ${failed.length} did not work`
  return { actions, lookups, context, failed, line }
}

/** Groups tool calls into "Today / Yesterday / Earlier" using the clock: events carry only a time, so a time that goes backwards starts an earlier day. */
export function groupByDay<T extends { ts: string }>(items: T[]): { label: string; items: T[] }[] {
  const days: T[][] = []
  let prev = ''
  for (const item of items) {
    if (days.length === 0 || item.ts < prev) days.push([])
    days[days.length - 1].push(item)
    prev = item.ts
  }
  return days.map((d, i) => {
    const fromEnd = days.length - 1 - i
    return { label: fromEnd === 0 ? 'Today' : fromEnd === 1 ? 'Yesterday' : 'Earlier', items: d }
  })
}
