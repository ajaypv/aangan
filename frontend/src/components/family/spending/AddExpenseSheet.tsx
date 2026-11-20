import { useState, type FormEvent } from 'react'
import { CATEGORIES } from '@/lib/money'
import { useApp } from '@/state/AppState'
import type { Snapshot } from '@/types'
import { Button, Field, inputClass } from '@/ui/primitives'
import { Sheet } from '@/ui/Sheet'

function Form({ snap, onDone }: { snap: Snapshot; onDone: () => void }) {
  const { callTool, busy, me } = useApp()
  const [amount, setAmount] = useState('')
  const [category, setCategory] = useState('groceries')
  const [note, setNote] = useState('')
  const [who, setWho] = useState(me && snap.members.some((m) => m.id === me) ? me : (snap.members[0]?.id ?? ''))
  const [date, setDate] = useState(snap.now.date)

  const value = Number(amount)
  const valid = Number.isFinite(value) && value > 0 && who !== '' && date !== '' && date <= snap.now.date

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!valid) return
    const ok = await callTool('money', 'log_expense', { member_id: who, amount: value, category, note: note.trim(), date }, 'Expense added.')
    if (ok) onDone()
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <Field label="Amount (₹)">
          <input required type="number" inputMode="decimal" min={1} step="any" className={`${inputClass} num`} value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="450" autoFocus />
        </Field>
        <Field label="Category">
          <select className={inputClass} value={category} onChange={(e) => setCategory(e.target.value)}>
            {CATEGORIES.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
        </Field>
      </div>
      <Field label="What was it for? (optional)">
        <input className={inputClass} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Weekly shop" autoComplete="off" />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Spent by">
          <select className={inputClass} value={who} onChange={(e) => setWho(e.target.value)}>
            {snap.members.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Date">
          <input required type="date" max={snap.now.date} className={inputClass} value={date} onChange={(e) => setDate(e.target.value)} />
        </Field>
      </div>
      <div className="flex justify-end gap-2 pt-1">
        <Button variant="tertiary" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" loading={busy} disabled={!valid}>
          Add expense
        </Button>
      </div>
    </form>
  )
}

export function AddExpenseSheet({ snap, open, onClose }: { snap: Snapshot; open: boolean; onClose: () => void }) {
  return (
    <Sheet open={open} title="Add an expense" onClose={onClose}>
      <Form snap={snap} onDone={onClose} />
    </Sheet>
  )
}
