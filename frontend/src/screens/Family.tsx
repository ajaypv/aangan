import { ChevronRight, Pencil, UserMinus, UserPlus, X } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { AddMemberSheet, MemberForm } from '@/components/family/MemberForm'
import { factTone, factsOf, familyFacts } from '@/lib/domain'
import { memberChips, statusLine } from '@/lib/household'
import { useApp } from '@/state/AppState'
import type { Member, MemoryFact, Snapshot } from '@/types'
import { Avatar, Button, Card, IconButton, ListCard, Pill, SectionHeader, inputClass } from '@/ui/primitives'
import { Sheet } from '@/ui/Sheet'

/** The things Aangan remembers about one person (or the whole family), each removable, with a box to teach it one more. */
function Facts({ about, facts, label }: { about: string; facts: MemoryFact[]; label: string }) {
  const { runTool, notify } = useApp()
  const [text, setText] = useState('')
  const [saving, setSaving] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)

  const add = async (e: FormEvent) => {
    e.preventDefault()
    if (!text.trim()) return
    setSaving(true)
    setProblem(null)
    const outcome = await runTool('household', 'remember_fact', { about, fact: text.trim() })
    setSaving(false)
    if (outcome.ok) {
      setText('')
      notify('success', 'Aangan will remember that.')
    } else setProblem(outcome.error ?? 'That could not be saved.')
  }

  const forget = async (f: MemoryFact) => {
    const outcome = await runTool('household', 'forget_fact', { fact_id: f.id })
    if (!outcome.ok) notify('error', outcome.error ?? 'That could not be removed.')
  }

  return (
    <div>
      {facts.length > 0 ? (
        <ul className="space-y-1.5" aria-label={label}>
          {facts.map((f) => (
            <li key={f.id} className="flex items-center justify-between gap-2">
              <Pill tone={factTone(f)} className="max-w-full whitespace-normal py-1 text-left text-sm">
                {f.fact}
              </Pill>
              <IconButton label={`Forget: ${f.fact}`} tooltip={false} onClick={() => void forget(f)}>
                <X className="size-4" aria-hidden="true" />
              </IconButton>
            </li>
          ))}
        </ul>
      ) : (
        <p className="t-secondary">Nothing yet. Add allergies, routines or preferences so Aangan uses them in every plan.</p>
      )}
      <form onSubmit={add} className="mt-3 flex gap-2">
        <label className="min-w-0 flex-1">
          <span className="sr-only">{`Add something to remember (${label})`}</span>
          <input
            className={inputClass}
            value={text}
            onChange={(e) => {
              setText(e.target.value)
              setProblem(null)
            }}
            placeholder="For example: allergic to eggs"
            autoComplete="off"
          />
        </label>
        <Button type="submit" variant="secondary" loading={saving} disabled={!text.trim()}>
          Remember
        </Button>
      </form>
      {problem && (
        <p role="alert" className="mt-1 text-xs font-semibold text-[var(--rw-text-danger)]">
          {problem}
        </p>
      )}
    </div>
  )
}

type PersonView = 'detail' | 'edit' | 'remove'

/** One person's sheet. Mounted with a key per person so it always opens on the overview. */
function PersonSheetBody({ member, onClose }: { member: Member; onClose: () => void }) {
  const { snap, config, personaId, runTool, notify } = useApp()
  const [view, setView] = useState<PersonView>('detail')
  const [removing, setRemoving] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  if (!snap) return null
  const isMe = member.id === personaId
  const onlyOne = snap.members.length <= 1
  const voice = config?.voices[member.id]

  const remove = async () => {
    setRemoving(true)
    setProblem(null)
    const outcome = await runTool('household', 'remove_member', { member_id: member.id, confirm: true })
    setRemoving(false)
    if (outcome.ok) {
      notify('success', `${member.name} was removed from the family.`)
      onClose()
    } else setProblem(outcome.error ?? `${member.name} could not be removed.`)
  }

  if (view === 'edit') {
    return <MemberForm variant="edit" initial={member} onDone={() => setView('detail')} onCancel={() => setView('detail')} />
  }

  if (view === 'remove') {
    return (
      <div className="space-y-4">
        <p>
          Remove <strong>{member.name}</strong> from the family? Their calendar entries, school and health records and everything Aangan remembers about them are deleted. This cannot be undone.
        </p>
        {problem && (
          <p role="alert" className="rounded-md border border-l-4 border-line border-l-[var(--rw-danger)] bg-danger-bg px-3 py-2 text-sm font-medium">
            {problem}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button variant="tertiary" onClick={() => setView('detail')} disabled={removing}>
            Cancel
          </Button>
          <Button variant="danger" loading={removing} onClick={() => void remove()}>
            Remove {member.name}
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <Avatar member={member} size={56} />
        <div className="min-w-0 flex-1">
          <p className="t-card flex items-center gap-2">
            {member.name} {isMe && <Pill tone="brand">You</Pill>}
          </p>
          <p className="t-secondary">
            {member.relation} · {member.age} years old
          </p>
          {voice && <p className="t-caption">{`Aangan's voice with them: ${voice.name}`}</p>}
        </div>
        <Button variant="secondary" icon={<Pencil className="size-4" aria-hidden="true" />} onClick={() => setView('edit')}>
          Edit
        </Button>
      </div>

      <section>
        <h3 className="t-card mb-2">What Aangan remembers</h3>
        <Facts about={member.id} facts={factsOf(snap, member.id)} label={`Remembered about ${member.name}`} />
      </section>

      <section className="border-t border-line pt-4">
        {onlyOne || isMe ? (
          <p className="t-caption">{onlyOne ? 'The only person in the household cannot be removed.' : 'This is the profile on this device. Switch to another profile in Settings before removing it.'}</p>
        ) : (
          <Button variant="tertiary" className="text-[var(--rw-text-danger)]" icon={<UserMinus className="size-4" aria-hidden="true" />} onClick={() => setView('remove')}>
            Remove from family
          </Button>
        )}
      </section>
    </div>
  )
}

function PersonRow({ snap, member, isMe, onOpen }: { snap: Snapshot; member: Member; isMe: boolean; onOpen: () => void }) {
  const chips = memberChips(snap, member)
  const shown = chips.slice(0, 3)
  return (
    <li>
      <button type="button" onClick={onOpen} className="flex min-h-[4.5rem] w-full items-start gap-3 px-4 py-3 text-left transition-colors hover:bg-hover">
        <Avatar member={member} size={44} />
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2">
            <span className="truncate font-semibold">{member.name}</span>
            {isMe && <Pill tone="brand">You</Pill>}
          </span>
          <span className="t-secondary block truncate">
            {member.relation} · {member.age} years old
          </span>
          <span className="block truncate text-sm">{statusLine(snap, member)}</span>
          {shown.length > 0 && (
            <span className="mt-1.5 flex flex-wrap gap-1.5">
              {shown.map((c) => (
                <Pill key={c.text} tone={c.tone} className="max-w-[16rem] truncate">
                  {c.text}
                </Pill>
              ))}
              {chips.length > shown.length && <Pill>{`+${chips.length - shown.length} more`}</Pill>}
            </span>
          )}
        </span>
        <ChevronRight className="mt-3 size-5 shrink-0 text-ink-2" aria-hidden="true" />
      </button>
    </li>
  )
}

/** The Family tab's People view. Schedule and spending live in the other views of the tab. */
export function Family() {
  const { snap, personaId, notify } = useApp()
  const [openId, setOpenId] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  if (!snap) return null
  const open = openId ? (snap.members.find((m) => m.id === openId) ?? null) : null
  const shared = familyFacts(snap)

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pb-8 pt-4 lg:px-8">
      <SectionHeader
        title="People"
        hint={`${snap.members.length} in your family`}
        action={
          <Button icon={<UserPlus className="size-4" aria-hidden="true" />} onClick={() => setAdding(true)}>
            Add person
          </Button>
        }
      />
      <ListCard aria-label="Family members">
        {snap.members.map((m) => (
          <PersonRow key={m.id} snap={snap} member={m} isMe={m.id === personaId} onOpen={() => setOpenId(m.id)} />
        ))}
      </ListCard>

      <section className="mt-8">
        <SectionHeader title="The whole family" hint="Routines and budgets that apply to everyone" as="h3" />
        <Card className="p-4">
          <Facts about="family" facts={shared} label="Remembered about the whole family" />
        </Card>
      </section>

      <Sheet open={open !== null} title={open?.name ?? ''} onClose={() => setOpenId(null)}>
        {open && <PersonSheetBody key={open.id} member={open} onClose={() => setOpenId(null)} />}
      </Sheet>
      <AddMemberSheet open={adding} onClose={() => setAdding(false)} onAdded={(m) => notify('success', `${m.name} joined the family.`)} />
    </div>
  )
}
