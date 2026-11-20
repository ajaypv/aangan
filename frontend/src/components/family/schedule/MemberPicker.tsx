import { cn } from '@/lib/utils'
import type { Member } from '@/types'
import { Avatar } from '@/ui/primitives'

/** Toggle chips for choosing one or more family members. */
export function MemberPicker({
  members,
  value,
  onChange,
  legend,
}: {
  members: Member[]
  value: string[]
  onChange: (next: string[]) => void
  legend: string
}) {
  const toggle = (id: string) => onChange(value.includes(id) ? value.filter((v) => v !== id) : [...value, id])
  return (
    <fieldset>
      <legend className="mb-1 text-sm font-semibold">{legend}</legend>
      <div className="flex flex-wrap gap-2">
        {members.map((m) => {
          const on = value.includes(m.id)
          return (
            <button
              key={m.id}
              type="button"
              aria-pressed={on}
              onClick={() => toggle(m.id)}
              className={cn(
                'inline-flex min-h-11 items-center gap-2 rounded-full border py-1 pl-1.5 pr-3.5 text-sm font-semibold transition-colors lg:min-h-9',
                on ? 'border-[var(--selected-edge)] bg-brand-soft text-brand-text' : 'border-edge bg-surface text-ink-2 hover:bg-hover',
              )}
            >
              <Avatar member={m} size={26} />
              {m.name}
            </button>
          )
        })}
      </div>
    </fieldset>
  )
}
