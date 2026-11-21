import { CalendarClock, Check, Circle, ListChecks, Plus, ShoppingBasket, Sparkles, X } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { dayPriorities, dueLabel, isOverdue, ownerName, readTasks, sortTasks } from '@/lib/tasks'
import { cn } from '@/lib/utils'
import { useApp } from '@/state/AppState'
import type { FamilyTask, Member, ShoppingList } from '@/types'
import { Avatar, Button, Card, EmptyState, IconButton, Pill, ScreenSkeleton, SectionHeader, SegmentedControl, inputClass } from '@/ui/primitives'

const selectClass = cn(inputClass, 'pr-8')

/** Everything the rest of the app needs to run one of this agent's tools and say what happened. */
function useTasksTool() {
  const { runTool, notify } = useApp()
  return async (tool: string, args: Record<string, unknown>, success?: string): Promise<{ ok: boolean; result: Record<string, unknown> }> => {
    const outcome = await runTool('tasks', tool, args)
    if (!outcome.ok) notify('error', outcome.error ?? 'That did not go through. Try again.')
    else if (success) notify('success', success)
    return outcome
  }
}

/** The person's day in a few lines: what they owe, what is on the calendar, the shopping they are on. */
function DayCard({ member }: { member: Member }) {
  const { snap } = useApp()
  if (!snap) return null
  const lines = dayPriorities(snap, member.id)
  const remembered = snap.memory.filter((f) => f.about === member.id).slice(0, 2)
  return (
    <Card className="space-y-2 p-4">
      <div className="flex items-center gap-2">
        <span className="grid size-8 shrink-0 place-items-center rounded-full bg-brand-soft text-brand-text" aria-hidden="true">
          <Sparkles className="size-4" />
        </span>
        <h3 className="t-card">{`Today for ${member.name}`}</h3>
      </div>
      {lines.length === 0 ? (
        <p className="t-secondary">A clear day: nothing scheduled and nothing pending.</p>
      ) : (
        <ol className="space-y-1.5" aria-label="Priorities for today">
          {lines.map((line, i) => (
            <li key={line} className="flex gap-2.5">
              <span className="num grid size-6 shrink-0 place-items-center rounded-full bg-surface-2 text-xs font-bold" aria-hidden="true">
                {i + 1}
              </span>
              <span className={cn('min-w-0 pt-0.5', line.startsWith('Overdue') && 'font-semibold text-[var(--rw-text-danger)]')}>{line}</span>
            </li>
          ))}
        </ol>
      )}
      {remembered.length > 0 && <p className="t-caption">{`Aangan remembers: ${remembered.map((f) => f.fact).join('; ')}.`}</p>}
    </Card>
  )
}

function ShoppingCard({ list, members }: { list: ShoppingList | null; members: Member[] }) {
  const { personaId } = useApp()
  const run = useTasksTool()
  const [text, setText] = useState('')
  const [saving, setSaving] = useState(false)
  const [warnings, setWarnings] = useState<string[]>([])
  const [shopper, setShopper] = useState('')
  const [assigning, setAssigning] = useState(false)
  const open = list?.items.filter((i) => !i.bought) ?? []
  const bought = list?.items.filter((i) => i.bought) ?? []
  const who = list?.assignee ? members.find((m) => m.id === list.assignee) : undefined

  const add = async (e: FormEvent) => {
    e.preventDefault()
    const items = text.split(/[,;\n]/).map((s) => s.trim()).filter(Boolean)
    if (!items.length) return
    setSaving(true)
    const outcome = await run('add_shopping_items', { items, added_by: personaId })
    setSaving(false)
    if (outcome.ok) {
      setText('')
      setWarnings((outcome.result.warnings as string[] | undefined) ?? [])
    }
  }

  const assign = async () => {
    if (!shopper) return
    setAssigning(true)
    const outcome = await run('assign_shopping', { assignee: shopper }, `${members.find((m) => m.id === shopper)?.name ?? 'They'} is on the shopping, and has been told.`)
    setAssigning(false)
    if (outcome.ok) setShopper('')
  }

  return (
    <Card className="space-y-3 p-4">
      <div className="flex items-center gap-2">
        <span className="grid size-8 shrink-0 place-items-center rounded-full bg-brand-soft text-brand-text" aria-hidden="true">
          <ShoppingBasket className="size-4" />
        </span>
        <h3 className="t-card min-w-0 flex-1">Shopping list</h3>
        {open.length > 0 && <Pill className="num">{open.length}</Pill>}
      </div>

      <form onSubmit={add} className="flex gap-2">
        <label className="min-w-0 flex-1">
          <span className="sr-only">Add to the shopping list</span>
          <input className={inputClass} value={text} onChange={(e) => setText(e.target.value)} placeholder="Add: milk, 2 kg rice, curd" autoComplete="off" />
        </label>
        <Button type="submit" icon={<Plus className="size-4" aria-hidden="true" />} loading={saving} disabled={!text.trim()}>
          Add
        </Button>
      </form>
      {warnings.length > 0 && (
        <div role="status" className="space-y-1 rounded-md border border-l-4 border-line border-l-[var(--rw-warning)] bg-warning-bg px-3 py-2 text-sm font-medium">
          {warnings.map((w) => (
            <p key={w}>{w}</p>
          ))}
        </div>
      )}

      {open.length === 0 ? (
        <p className="t-secondary">Nothing to buy. Add what the family needs, or just tell Aangan: "we need milk".</p>
      ) : (
        <ul className="divide-y divide-line rounded-md border border-line" aria-label="Still to buy">
          {open.map((item) => (
            <li key={item.id} className="flex items-center gap-1">
              <button
                type="button"
                className="flex min-h-11 min-w-0 flex-1 items-center gap-3 px-3 text-left hover:bg-hover"
                onClick={() => void run('mark_bought', { items: [item.name], bought_by: personaId })}
                aria-label={`Mark ${item.name} as bought`}
              >
                <Circle className="size-5 shrink-0 text-ink-2" aria-hidden="true" />
                <span className="min-w-0 flex-1 truncate font-medium">{item.name}</span>
                {item.qty && <span className="t-secondary num shrink-0">{item.qty}</span>}
              </button>
              <IconButton label={`Take ${item.name} off the list`} tooltip={false} onClick={() => void run('remove_shopping_items', { items: [item.name] })}>
                <X className="size-4" aria-hidden="true" />
              </IconButton>
            </li>
          ))}
        </ul>
      )}

      {bought.length > 0 && (
        <details className="rounded-md border border-line">
          <summary className="flex min-h-11 cursor-pointer list-none items-center px-3 text-sm font-semibold">{`Bought (${bought.length})`}</summary>
          <ul className="divide-y divide-line border-t border-line">
            {bought.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className="flex min-h-11 w-full items-center gap-3 px-3 text-left text-ink-2 hover:bg-hover"
                  onClick={() => void run('add_shopping_items', { items: [item.name], added_by: personaId })}
                  aria-label={`${item.name} was bought: tap to put it back on the list`}
                >
                  <Check className="size-5 shrink-0 text-[var(--rw-text-success)]" aria-hidden="true" />
                  <span className="min-w-0 flex-1 truncate line-through">{item.name}</span>
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}

      <div className="space-y-2 border-t border-line pt-3">
        {who ? (
          <p className="flex items-center gap-2 text-sm">
            <Avatar member={who} size={24} />
            <span>
              <strong>{who.name}</strong> is doing the shopping
            </span>
          </p>
        ) : (
          <p className="t-secondary">Nobody is shopping yet. Pick who goes, and they get the list.</p>
        )}
        <div className="flex gap-2">
          <label className="min-w-0 flex-1">
            <span className="sr-only">Who does the shopping</span>
            <select className={selectClass} value={shopper} onChange={(e) => setShopper(e.target.value)} disabled={open.length === 0}>
              <option value="">{who ? 'Pass it to someone else' : 'Who goes shopping?'}</option>
              {members.filter((m) => m.id !== who?.id).map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))}
            </select>
          </label>
          <Button variant="secondary" loading={assigning} disabled={!shopper || open.length === 0} onClick={() => void assign()}>
            Assign
          </Button>
        </div>
      </div>
    </Card>
  )
}

function TaskRow({ task, members, onRun }: { task: FamilyTask; members: Member[]; onRun: ReturnType<typeof useTasksTool> }) {
  const { snap } = useApp()
  if (!snap) return null
  const overdue = isOverdue(snap, task)
  const owner = task.assignee && task.assignee !== 'family' ? members.find((m) => m.id === task.assignee) : undefined
  return (
    <li className="flex items-start gap-1">
      <button
        type="button"
        className="grid min-h-11 w-11 shrink-0 place-items-center text-ink-2 hover:text-[var(--rw-text-success)]"
        onClick={() => void onRun('complete_task', { task: task.id })}
        aria-label={`Mark done: ${task.title}`}
      >
        <Circle className="size-5" aria-hidden="true" />
      </button>
      <div className="min-w-0 flex-1 py-2">
        <p className="font-medium leading-snug">{task.title}</p>
        <div className="mt-1 flex flex-wrap items-center gap-1.5">
          {task.due && (
            <Pill tone={overdue ? 'danger' : task.due === snap.now.date ? 'warning' : 'neutral'}>
              <CalendarClock className="size-3" aria-hidden="true" />
              {dueLabel(snap, task)}
            </Pill>
          )}
          {task.priority === 'high' && <Pill tone="danger">High</Pill>}
          {task.list && <Pill tone="info">Shopping</Pill>}
          <span className="inline-flex items-center gap-1 text-xs text-ink-2">
            {owner && <Avatar member={owner} size={18} />}
            {ownerName(task, members)}
          </span>
        </div>
        {task.note && <p className="t-caption mt-1">{task.note}</p>}
      </div>
      <label className="shrink-0 py-0.5">
        <span className="sr-only">{`Who does: ${task.title}`}</span>
        <select
          className="min-h-11 w-24 rounded-md border border-transparent bg-transparent px-1 text-sm text-ink-2 hover:border-edge focus-visible:outline-2"
          value=""
          onChange={(e) => e.target.value && void onRun('assign_task', { task: task.id, assignee: e.target.value }, `Passed it to ${ownerName({ assignee: e.target.value }, members)}.`)}
        >
          <option value="">Reassign</option>
          {members.filter((m) => m.id !== task.assignee).map((m) => (
            <option key={m.id} value={m.id}>
              {m.name}
            </option>
          ))}
          {task.assignee !== 'family' && <option value="family">Anyone</option>}
        </select>
      </label>
      <IconButton label={`Delete the task: ${task.title}`} tooltip={false} onClick={() => void onRun('remove_task', { task: task.id })}>
        <X className="size-4" aria-hidden="true" />
      </IconButton>
    </li>
  )
}

function TasksCard({ tasks, members }: { tasks: FamilyTask[]; members: Member[] }) {
  const { snap, personaId } = useApp()
  const run = useTasksTool()
  const [scope, setScope] = useState<'mine' | 'everyone'>('mine')
  const [title, setTitle] = useState('')
  const [assignee, setAssignee] = useState('')
  const [due, setDue] = useState('')
  const [saving, setSaving] = useState(false)
  if (!snap) return null
  const mine = (t: FamilyTask) => t.assignee === personaId || t.assignee === 'family'
  const open = sortTasks(tasks.filter((t) => !t.done && (scope === 'everyone' || mine(t))))
  const done = tasks.filter((t) => t.done).slice(-5).reverse()
  const unassigned = tasks.filter((t) => !t.done && !t.assignee).length

  const add = async (e: FormEvent) => {
    e.preventDefault()
    if (!title.trim()) return
    setSaving(true)
    const who = members.find((m) => m.id === assignee)
    const outcome = await run('add_task', { title: title.trim(), assignee: assignee || undefined, due: due || undefined }, who && who.id !== personaId ? `Task given to ${who.name}, who has been told.` : 'Task added.')
    setSaving(false)
    if (outcome.ok) {
      setTitle('')
      setDue('')
    }
  }

  return (
    <Card className="space-y-3 p-4">
      <div className="flex items-center gap-2">
        <span className="grid size-8 shrink-0 place-items-center rounded-full bg-brand-soft text-brand-text" aria-hidden="true">
          <ListChecks className="size-4" />
        </span>
        <h3 className="t-card min-w-0 flex-1">Tasks</h3>
        {open.length > 0 && <Pill className="num">{open.length}</Pill>}
      </div>

      <SegmentedControl<'mine' | 'everyone'>
        label="Whose tasks"
        value={scope}
        onChange={setScope}
        options={[
          { value: 'mine', label: 'Mine' },
          { value: 'everyone', label: unassigned ? `Everyone (${unassigned} unassigned)` : 'Everyone' },
        ]}
      />

      <form onSubmit={add} className="space-y-2">
        <label className="block">
          <span className="sr-only">New task</span>
          <input className={inputClass} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="New task: pay the water bill" autoComplete="off" />
        </label>
        <div className="flex flex-wrap gap-2">
          <label className="min-w-[8rem] flex-1">
            <span className="sr-only">Give it to</span>
            <select className={selectClass} value={assignee} onChange={(e) => setAssignee(e.target.value)}>
              <option value="">Nobody yet</option>
              <option value="family">Anyone</option>
              {members.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.id === personaId ? `${m.name} (me)` : m.name}
                </option>
              ))}
            </select>
          </label>
          <label className="min-w-[8rem] flex-1">
            <span className="sr-only">Due date</span>
            <input type="date" className={inputClass} value={due} min={snap.now.date} onChange={(e) => setDue(e.target.value)} />
          </label>
          <Button type="submit" icon={<Plus className="size-4" aria-hidden="true" />} loading={saving} disabled={!title.trim()}>
            Add
          </Button>
        </div>
      </form>

      {open.length === 0 ? (
        <p className="t-secondary">{scope === 'mine' ? 'Nothing pending for you.' : 'Nothing pending for the family.'}</p>
      ) : (
        <ul className="divide-y divide-line rounded-md border border-line" aria-label="Pending tasks">
          {open.map((t) => (
            <TaskRow key={t.id} task={t} members={members} onRun={run} />
          ))}
        </ul>
      )}

      {done.length > 0 && (
        <details className="rounded-md border border-line">
          <summary className="flex min-h-11 cursor-pointer list-none items-center px-3 text-sm font-semibold">{`Done recently (${done.length})`}</summary>
          <ul className="divide-y divide-line border-t border-line">
            {done.map((t) => (
              <li key={t.id} className="flex min-h-11 items-center gap-3 px-3 text-ink-2">
                <Check className="size-5 shrink-0 text-[var(--rw-text-success)]" aria-hidden="true" />
                <span className="min-w-0 flex-1 truncate line-through">{t.title}</span>
                <span className="t-caption shrink-0">{ownerName(t, members)}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </Card>
  )
}

/** The Family tab's Tasks view: your day, the shared shopping list, and who is doing what. */
export function TasksView() {
  const { snap, member } = useApp()
  if (!snap) return <ScreenSkeleton />
  const { tasks, lists } = readTasks(snap)
  const list = lists.find((l) => l.id === 'groceries') ?? lists[0] ?? null
  return (
    <div className="mx-auto w-full max-w-3xl px-4 pb-8 pt-4 lg:px-8">
      <SectionHeader title="Tasks and shopping" hint="Who is doing what, and what the family needs" />
      {snap.members.length === 0 ? (
        <EmptyState title="Add your family first" icon={<ListChecks className="size-5" aria-hidden="true" />}>
          Tasks and shopping are shared. Add the people in your household and then give them things to do.
        </EmptyState>
      ) : (
        <div className="space-y-4">
          {member && <DayCard member={member} />}
          <ShoppingCard list={list} members={snap.members} />
          <TasksCard tasks={tasks} members={snap.members} />
        </div>
      )}
    </div>
  )
}
