import { useState, type FormEvent } from 'react'
import { CATEGORIES, categoryOf, formatINR } from '@/lib/money'
import { useApp } from '@/state/AppState'
import { Button, Field, inputClass } from '@/ui/primitives'
import { Sheet } from '@/ui/Sheet'

function Form({ budgets, onDone }: { budgets: Record<string, number | null>; onDone: () => void }) {
  const { callTool, busy } = useApp()
  const [scope, setScope] = useState('total')
  const [amount, setAmount] = useState(budgets.total ? String(budgets.total) : '')
  const value = Number(amount)
  const valid = Number.isFinite(value) && value > 0
  const current = Object.entries(budgets).filter(([, v]) => v)

  const pick = (key: string) => {
    setScope(key)
    setAmount(budgets[key] ? String(budgets[key]) : '')
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!valid) return
    const label = scope === 'total' ? 'The monthly budget' : `The ${categoryOf(scope).label.toLowerCase()} budget`
    const ok = await callTool('money', 'set_budget', { category: scope, amount: value }, `${label} is now ${formatINR(value)}.`)
    if (ok) onDone()
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <Field label="Budget for">
          <select className={inputClass} value={scope} onChange={(e) => pick(e.target.value)}>
            <option value="total">Everything (monthly total)</option>
            {CATEGORIES.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Per month (₹)">
          <input required type="number" inputMode="decimal" min={1} step="any" className={`${inputClass} num`} value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="60000" />
        </Field>
      </div>

      {current.length > 0 && (
        <div>
          <p className="mb-1.5 text-sm font-semibold">Current budgets</p>
          <ul className="divide-y divide-line overflow-hidden rounded-lg border border-line">
            {current.map(([key, v]) => (
              <li key={key}>
                <button type="button" onClick={() => pick(key)} className="flex min-h-11 w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm hover:bg-hover">
                  <span className="font-semibold">{key === 'total' ? 'Monthly total' : categoryOf(key).label}</span>
                  <span className="num text-ink-2">{formatINR(v as number)}</span>
                </button>
              </li>
            ))}
          </ul>
          <p className="t-caption mt-1.5">Tap one to change it.</p>
        </div>
      )}

      <div className="flex justify-end gap-2">
        <Button variant="tertiary" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" loading={busy} disabled={!valid}>
          Save budget
        </Button>
      </div>
    </form>
  )
}

export function BudgetSheet({ budgets, open, onClose }: { budgets: Record<string, number | null>; open: boolean; onClose: () => void }) {
  return (
    <Sheet open={open} title="Monthly budgets" onClose={onClose}>
      <Form budgets={budgets} onDone={onClose} />
    </Sheet>
  )
}
