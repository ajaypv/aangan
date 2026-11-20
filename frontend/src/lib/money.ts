import {
  Car,
  CircleEllipsis,
  Clapperboard,
  GraduationCap,
  HeartPulse,
  Plane,
  Receipt,
  ShoppingBag,
  ShoppingBasket,
  UtensilsCrossed,
  type LucideIcon,
} from 'lucide-react'
import { addDays, dayLabel } from '@/lib/format'
import type { Snapshot } from '@/types'

export interface Expense {
  id: string
  member_id: string
  amount: number
  category: string
  note: string
  date: string
  source?: string
}

export interface MoneyDomain {
  expenses: Expense[]
  budgets: Record<string, number | null>
  currency: string
}

export interface CategoryInfo {
  id: string
  label: string
  icon: LucideIcon
}

/** The ten categories the money agent understands, in the order shown in forms. */
export const CATEGORIES: CategoryInfo[] = [
  { id: 'groceries', label: 'Groceries', icon: ShoppingBasket },
  { id: 'eating out', label: 'Eating out', icon: UtensilsCrossed },
  { id: 'transport', label: 'Transport and fuel', icon: Car },
  { id: 'bills', label: 'Bills and utilities', icon: Receipt },
  { id: 'health', label: 'Health and pharmacy', icon: HeartPulse },
  { id: 'education', label: 'Education', icon: GraduationCap },
  { id: 'shopping', label: 'Shopping', icon: ShoppingBag },
  { id: 'entertainment', label: 'Entertainment', icon: Clapperboard },
  { id: 'travel', label: 'Travel', icon: Plane },
  { id: 'other', label: 'Other', icon: CircleEllipsis },
]

export const categoryOf = (id: string): CategoryInfo =>
  CATEGORIES.find((c) => c.id === id) ?? { id, label: id ? id[0].toUpperCase() + id.slice(1) : 'Other', icon: CircleEllipsis }

const inr = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 })
export const formatINR = (n: number) => inr.format(Math.round(n))

/** Rewrites the backend's "Rs 1,800" wording in tips into the rupee sign used everywhere else on screen. */
export const rupeeText = (text: string) => text.replace(/\bRs\.?\s?(?=\d)/g, '₹')

/** The money ledger from the snapshot, with safe defaults when the household has not logged anything. */
export function readMoney(snap: Snapshot): MoneyDomain {
  const raw = (snap.domains as Record<string, unknown>).money as Partial<MoneyDomain> | undefined
  return {
    expenses: Array.isArray(raw?.expenses) ? raw.expenses : [],
    budgets: raw?.budgets && typeof raw.budgets === 'object' ? raw.budgets : {},
    currency: raw?.currency ?? 'INR',
  }
}

export type Period = 'month' | 'last_month' | 'all'
export const PERIOD_LABEL: Record<Period, string> = { month: 'This month', last_month: 'Last month', all: 'All' }

export interface DateRange {
  start: string
  end: string
}

const monthStart = (iso: string) => `${iso.slice(0, 8)}01`
const monthBefore = (iso: string): DateRange => {
  const end = addDays(monthStart(iso), -1)
  return { start: monthStart(end), end }
}

/** Date range of a period, plus the range before it (for "up 12% on last month"). ISO dates compare as strings. */
export function periodRange(today: string, period: Period): { range: DateRange; previous: DateRange | null } {
  if (period === 'month') return { range: { start: monthStart(today), end: today }, previous: monthBefore(today) }
  if (period === 'last_month') {
    const range = monthBefore(today)
    return { range, previous: monthBefore(range.start) }
  }
  return { range: { start: '0000-01-01', end: today }, previous: null }
}

export const inRange = (e: Expense, r: DateRange) => e.date >= r.start && e.date <= r.end
export const totalOf = (rows: Expense[]) => rows.reduce((sum, e) => sum + e.amount, 0)

export const ledgerStart = (rows: Expense[]): string | null => rows.reduce<string | null>((first, e) => (first === null || e.date < first ? e.date : first), null)

export interface CategoryTotal {
  id: string
  amount: number
  share: number
}

export function byCategory(rows: Expense[]): CategoryTotal[] {
  const total = totalOf(rows)
  const sums = new Map<string, number>()
  for (const e of rows) sums.set(e.category, (sums.get(e.category) ?? 0) + e.amount)
  return [...sums.entries()].map(([id, amount]) => ({ id, amount, share: total ? Math.round((amount / total) * 100) : 0 })).sort((a, b) => b.amount - a.amount)
}

export function byMember(rows: Expense[]): { id: string; amount: number }[] {
  const sums = new Map<string, number>()
  for (const e of rows) sums.set(e.member_id, (sums.get(e.member_id) ?? 0) + e.amount)
  return [...sums.entries()].map(([id, amount]) => ({ id, amount })).sort((a, b) => b.amount - a.amount)
}

/** The change against the previous period, only when the ledger really reaches back to the start of that period (as the agent does). */
export function comparison(rows: Expense[], total: number, previous: DateRange | null): { previous: number; changePct: number } | null {
  const first = ledgerStart(rows)
  if (!previous || !first || first > previous.start) return null
  const prevTotal = totalOf(rows.filter((e) => inRange(e, previous)))
  if (prevTotal <= 0) return null
  return { previous: prevTotal, changePct: Math.round(((total - prevTotal) / prevTotal) * 100) }
}

export interface BudgetState {
  pct: number
  tone: 'ok' | 'warning' | 'over'
  /** Positive when there is money left, negative when over. */
  left: number
}

export function budgetState(spent: number, budget: number): BudgetState {
  const pct = budget > 0 ? (spent / budget) * 100 : 0
  return { pct, tone: pct >= 100 ? 'over' : pct >= 85 ? 'warning' : 'ok', left: budget - spent }
}

const idNumber = (id: string) => Number(id.split('-')[1]) || 0

export interface DayGroup {
  date: string
  heading: string
  total: number
  items: Expense[]
}

export function dayHeading(date: string, today: string) {
  if (date === today) return 'Today'
  if (date === addDays(today, -1)) return 'Yesterday'
  return dayLabel(date)
}

/** Newest day first, newest entry first inside a day. */
export function groupByDay(rows: Expense[], today: string): DayGroup[] {
  const sorted = [...rows].sort((a, b) => (a.date === b.date ? idNumber(b.id) - idNumber(a.id) : b.date.localeCompare(a.date)))
  const groups: DayGroup[] = []
  for (const e of sorted) {
    const last = groups[groups.length - 1]
    if (last && last.date === e.date) {
      last.items.push(e)
      last.total += e.amount
    } else groups.push({ date: e.date, heading: dayHeading(e.date, today), total: e.amount, items: [e] })
  }
  return groups
}
