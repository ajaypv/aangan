import { Plus, Target, Undo2, Wallet, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { PERIOD_LABEL, byCategory, categoryOf, comparison, formatINR, inRange, periodRange, readMoney, totalOf, type Expense, type Period } from '@/lib/money'
import { useApp } from '@/state/AppState'
import { Button, Card, EmptyState, IconButton, ScreenSkeleton, SectionHeader, SegmentedControl } from '@/ui/primitives'
import { AddExpenseSheet } from './spending/AddExpenseSheet'
import { BudgetSheet } from './spending/BudgetSheet'
import { CategoryBars } from './spending/CategoryBars'
import { ExpenseList } from './spending/ExpenseList'
import { SavingsCard } from './spending/SavingsCard'
import { SummaryCard } from './spending/SummaryCard'

const UNDO_MS = 9000

/** What the family spends and where it goes: this month, last month or everything, with budgets and saving ideas. */
export function SpendingView() {
  const { snap, callTool } = useApp()
  const [period, setPeriod] = useState<Period>('month')
  const [adding, setAdding] = useState(false)
  const [budgeting, setBudgeting] = useState(false)
  const [undo, setUndo] = useState<Expense | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)

  // The undo offer fades after a few seconds.
  useEffect(() => {
    if (!undo) return
    const id = window.setTimeout(() => setUndo(null), UNDO_MS)
    return () => window.clearTimeout(id)
  }, [undo])

  if (!snap) return <ScreenSkeleton />

  const money = readMoney(snap)
  const { range, previous } = periodRange(snap.now.date, period)
  const rows = money.expenses.filter((e) => inRange(e, range))
  const total = totalOf(rows)
  const cats = byCategory(rows)
  const change = comparison(money.expenses, total, previous)
  const budgetTotal = money.budgets.total || null
  const empty = money.expenses.length === 0

  const remove = async (e: Expense) => {
    setDeleting(e.id)
    const ok = await callTool('money', 'delete_expense', { expense_id: e.id }, 'Expense deleted.')
    setDeleting(null)
    if (ok) setUndo(e)
  }
  const restore = async () => {
    if (!undo) return
    const e = undo
    setUndo(null)
    await callTool('money', 'log_expense', { member_id: e.member_id, amount: e.amount, category: e.category, note: e.note, date: e.date }, 'Expense restored.')
  }

  const actions = (
    <div className="flex flex-wrap gap-2">
      <Button variant="secondary" icon={<Target className="size-4" aria-hidden="true" />} onClick={() => setBudgeting(true)}>
        Budget
      </Button>
      <Button icon={<Plus className="size-4" aria-hidden="true" />} onClick={() => setAdding(true)}>
        Add expense
      </Button>
    </div>
  )

  return (
    <div className="mx-auto w-full max-w-6xl px-4 pb-8 pt-4 lg:px-8">
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h2 className="t-section">Spending</h2>
          <p className="t-secondary">What the family spends and where it goes</p>
        </div>
        {actions}
      </div>

      {empty ? (
        <EmptyState
          icon={<Wallet className="size-6" aria-hidden="true" />}
          title="No spending logged yet"
          action={
            <Button icon={<Plus className="size-4" aria-hidden="true" />} onClick={() => setAdding(true)}>
              Add expense
            </Button>
          }
        >
          Tell Aangan: <span className="font-semibold text-ink">“I spent 450 on groceries”</span>. Or add one here, and Aangan will answer questions about it and suggest ways to save.
        </EmptyState>
      ) : (
        <>
          <SegmentedControl
            label="Period"
            className="mb-4"
            value={period}
            onChange={setPeriod}
            options={(Object.keys(PERIOD_LABEL) as Period[]).map((p) => ({ value: p, label: PERIOD_LABEL[p] }))}
          />

          <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-2 lg:items-start">
            <div className="min-w-0 space-y-4">
              <SummaryCard snap={snap} period={period} rows={rows} total={total} change={change} budgetTotal={budgetTotal} onSetBudget={() => setBudgeting(true)} />
              <CategoryBars cats={cats} budgets={money.budgets} showBudgets={period !== 'all'} />
              <SavingsCard />
            </div>
            <section aria-label="Recent spending" className="min-w-0">
              <SectionHeader as="h3" title="Recent spending" hint={`${rows.length} ${rows.length === 1 ? 'entry' : 'entries'} · ${formatINR(total)}`} />
              <ExpenseList snap={snap} rows={rows} deleting={deleting} onDelete={remove} />
            </section>
          </div>
        </>
      )}

      {undo && (
        <div className="sticky bottom-3 z-20 mt-4 flex justify-center" role="status" aria-live="polite">
          <Card className="flex w-full max-w-md items-center gap-2 px-3 py-2 shadow-md">
            <span className="min-w-0 flex-1 truncate text-sm">
              Deleted {formatINR(undo.amount)} for {undo.note || categoryOf(undo.category).label}.
            </span>
            <Button variant="tertiary" size="sm" icon={<Undo2 className="size-4" aria-hidden="true" />} onClick={restore}>
              Undo
            </Button>
            <IconButton label="Dismiss" tooltip={false} onClick={() => setUndo(null)}>
              <X className="size-4" aria-hidden="true" />
            </IconButton>
          </Card>
        </div>
      )}

      <AddExpenseSheet snap={snap} open={adding} onClose={() => setAdding(false)} />
      <BudgetSheet budgets={money.budgets} open={budgeting} onClose={() => setBudgeting(false)} />
    </div>
  )
}
