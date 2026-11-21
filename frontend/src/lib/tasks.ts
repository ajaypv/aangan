import { addDays, dayLabel } from '@/lib/format'
import type { FamilyTask, Member, ShoppingList, Snapshot } from '@/types'

const PRIORITY_RANK = { high: 0, normal: 1, low: 2 } as const

/** The family's tasks and shopping lists as the backend keeps them, never undefined. */
export function readTasks(snap: Snapshot): { tasks: FamilyTask[]; lists: ShoppingList[] } {
  const d = snap.domains.tasks
  return { tasks: d?.tasks ?? [], lists: Object.values(d?.lists ?? {}) }
}

export const isOverdue = (snap: Snapshot, t: FamilyTask) => Boolean(t.due && !t.done && t.due < snap.now.date)

/** "Today", "Tomorrow", "Overdue since Thu 19 Nov" or "Mon 23 Nov". */
export function dueLabel(snap: Snapshot, t: FamilyTask): string {
  if (!t.due) return ''
  const label = t.due === snap.now.date ? 'Today' : t.due === addDays(snap.now.date, 1) ? 'Tomorrow' : dayLabel(t.due)
  return isOverdue(snap, t) ? `Overdue since ${dayLabel(t.due)}` : t.time ? `${label} ${t.time}` : label
}

/** Open tasks first, overdue and soonest on top, then by priority. */
export function sortTasks(tasks: FamilyTask[]): FamilyTask[] {
  return [...tasks].sort((a, b) => Number(a.done) - Number(b.done) || (a.due ?? '9999').localeCompare(b.due ?? '9999') || PRIORITY_RANK[a.priority] - PRIORITY_RANK[b.priority] || a.id.localeCompare(b.id, undefined, { numeric: true }))
}

/** Who a task belongs to, in words. */
export function ownerName(task: Pick<FamilyTask, 'assignee'>, members: Member[]): string {
  if (!task.assignee) return 'Nobody yet'
  if (task.assignee === 'family') return 'Anyone'
  return members.find((m) => m.id === task.assignee)?.name ?? task.assignee
}

/** What this person has to do today, most urgent first: tasks they owe, the next events, the shopping they are on. */
export function dayPriorities(snap: Snapshot, memberId: string): string[] {
  const { tasks, lists } = readTasks(snap)
  const mine = tasks.filter((t) => !t.done && (t.assignee === memberId || t.assignee === 'family'))
  const today = snap.now.date
  const out: string[] = []
  for (const t of sortTasks(mine.filter((x) => x.due && x.due < today))) out.push(`Overdue: ${t.title}`)
  for (const t of sortTasks(mine.filter((x) => x.due === today))) out.push(`Today: ${t.title}${t.time ? ` at ${t.time}` : ''}`)
  for (const e of snap.calendar.filter((x) => x.date === today && x.member_ids.includes(memberId)).sort((a, b) => a.start.localeCompare(b.start)).slice(0, 2)) out.push(`${e.start} ${e.title}`)
  for (const l of lists.filter((x) => x.assignee === memberId)) {
    const open = l.items.filter((i) => !i.bought).length
    if (open) out.push(`Shopping: ${open} ${open === 1 ? 'item' : 'items'} on the ${l.name} list`)
  }
  return out.slice(0, 6)
}
