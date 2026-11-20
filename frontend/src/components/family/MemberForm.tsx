import { ChevronDown } from 'lucide-react'
import { useId, useState, type FormEvent, type ReactNode } from 'react'
import { DIET_OPTIONS, RELATION_SUGGESTIONS, ROLES, draftToArgs, guessGender, memberToDraft, validateDraft, emptyDraft, type DraftErrors, type FormVariant, type MemberDraft } from '@/lib/household'
import { cn } from '@/lib/utils'
import { useApp } from '@/state/AppState'
import type { Member, MemberGender } from '@/types'
import { Button, Field, inputClass } from '@/ui/primitives'
import { Sheet } from '@/ui/Sheet'

function FieldError({ children }: { children?: string }) {
  if (!children) return null
  return (
    <p role="alert" className="mt-1 text-xs font-semibold text-[var(--rw-text-danger)]">
      {children}
    </p>
  )
}

/** A short list of big, tappable options where exactly one is chosen. */
function Choices<T extends string>({
  legend,
  hint,
  value,
  onChange,
  options,
  error,
  columns = 2,
}: {
  legend: string
  hint?: string
  value: T | ''
  onChange: (next: T) => void
  options: { value: T; label: string; hint?: string }[]
  error?: string
  columns?: 2 | 3
}) {
  return (
    <fieldset>
      <legend className="mb-1 text-sm font-semibold">{legend}</legend>
      <div role="radiogroup" aria-label={legend} className={cn('grid gap-2', columns === 3 ? 'grid-cols-3' : 'grid-cols-2')}>
        {options.map((o) => {
          const on = o.value === value
          return (
            <button
              key={o.value}
              type="button"
              role="radio"
              aria-checked={on}
              onClick={() => onChange(o.value)}
              className={cn(
                'min-h-11 rounded-md border px-3 py-2 text-left transition-colors',
                on ? 'border-[var(--selected-edge)] bg-brand-soft' : 'border-edge bg-surface hover:bg-hover',
              )}
            >
              <span className={cn('block text-sm font-semibold', on && 'text-brand-text')}>{o.label}</span>
              {o.hint && <span className="t-caption block">{o.hint}</span>}
            </button>
          )
        })}
      </div>
      {hint && !error && <p className="t-caption mt-1">{hint}</p>}
      <FieldError>{error}</FieldError>
    </fieldset>
  )
}

const VOICE_OPTIONS: { value: MemberGender; label: string }[] = [
  { value: 'female', label: 'Female voice' },
  { value: 'male', label: 'Male voice' },
]

/**
 * One form for adding yourself (`self`), adding someone else (`other`) and editing a profile (`edit`). It talks to the household tools
 * itself, keeps what was typed when something goes wrong, and shows the problem on the form.
 */
export function MemberForm({
  variant,
  initial,
  submitLabel,
  onDone,
  onCancel,
  autoFocus = true,
  submitVariant = 'primary',
}: {
  variant: FormVariant
  /** Required for `edit`. */
  initial?: Member
  submitLabel?: string
  /** Use `secondary` when another button on the same screen is the primary action. */
  submitVariant?: 'primary' | 'secondary'
  /** Called with the saved person once the backend accepted the change. */
  onDone: (member: Member) => void
  onCancel?: () => void
  autoFocus?: boolean
}) {
  const { runTool } = useApp()
  const [draft, setDraft] = useState<MemberDraft>(() => (initial ? memberToDraft(initial) : emptyDraft()))
  const [touched, setTouched] = useState(false)
  const [saving, setSaving] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const [genderTouched, setGenderTouched] = useState(false)
  const listId = useId()

  const errors: DraftErrors = touched ? validateDraft(draft, variant) : {}
  const set = <K extends keyof MemberDraft>(key: K, value: MemberDraft[K]) => {
    setDraft((d) => ({ ...d, [key]: value }))
    setProblem(null)
  }

  const onRelation = (relation: string) => {
    setDraft((d) => ({ ...d, relation, gender: genderTouched || !guessGender(relation) ? d.gender : guessGender(relation) }))
    setProblem(null)
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setTouched(true)
    if (Object.keys(validateDraft(draft, variant)).length > 0) return
    setSaving(true)
    setProblem(null)
    const args = draftToArgs(draft, variant)
    const outcome =
      variant === 'edit' && initial
        ? await runTool('household', 'update_member', {
            member_id: initial.id,
            name: args.name,
            relation: args.relation,
            age: args.age,
            ...(args.gender ? { gender: args.gender } : {}),
          })
        : await runTool('household', 'add_member', { ...args })
    setSaving(false)
    const member = outcome.result.member as Member | undefined
    if (outcome.ok && member) onDone(member)
    else setProblem(outcome.error ?? 'That could not be saved. Please try again.')
  }

  const label = submitLabel ?? (variant === 'edit' ? 'Save changes' : variant === 'self' ? 'Continue' : 'Add to family')
  const extras: ReactNode =
    variant === 'edit' ? null : (
      <details className="group rounded-md border border-line">
        <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 px-3 text-sm font-semibold lg:min-h-9">
          Allergies, diet and notes
          <span className="t-caption flex items-center gap-1 font-normal">
            Optional <ChevronDown className="size-4 transition-transform group-open:rotate-180" aria-hidden="true" />
          </span>
        </summary>
        <div className="space-y-3 border-t border-line p-3">
          <Field label="Allergies" hint="Separate with commas, for example peanuts, eggs. Aangan will never suggest food that clashes.">
            <input className={inputClass} value={draft.allergies} onChange={(e) => set('allergies', e.target.value)} autoComplete="off" />
          </Field>
          <Field label="Diet">
            <select className={inputClass} value={draft.diet} onChange={(e) => set('diet', e.target.value)}>
              {DIET_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Anything else worth remembering" hint="For example: bad knees, loves cricket, early dinner.">
            <input className={inputClass} value={draft.notes} onChange={(e) => set('notes', e.target.value)} autoComplete="off" />
          </Field>
        </div>
      </details>
    )

  return (
    <form onSubmit={submit} noValidate className="space-y-4">
      <div>
        <Field label={variant === 'self' ? 'Your name' : 'Name'}>
          <input
            className={inputClass}
            value={draft.name}
            onChange={(e) => set('name', e.target.value)}
            autoComplete={variant === 'self' ? 'given-name' : 'off'}
            autoCapitalize="words"
            autoFocus={autoFocus}
            aria-invalid={errors.name ? true : undefined}
            maxLength={60}
          />
        </Field>
        <FieldError>{errors.name}</FieldError>
      </div>

      {variant === 'self' ? (
        <Choices
          legend="I am a"
          value={draft.role}
          onChange={(role) => set('role', role)}
          options={ROLES.map((r) => ({ value: r.value, label: r.label, hint: r.hint }))}
          error={errors.role}
        />
      ) : (
        <div>
          <Field label="How are they related to you?" hint={variant === 'other' ? 'For example Daughter, Grandfather, Wife.' : undefined}>
            <input
              className={inputClass}
              list={listId}
              value={draft.relation}
              onChange={(e) => onRelation(e.target.value)}
              autoComplete="off"
              aria-invalid={errors.relation ? true : undefined}
            />
          </Field>
          <datalist id={listId}>
            {RELATION_SUGGESTIONS.map((r) => (
              <option key={r} value={r} />
            ))}
          </datalist>
          <FieldError>{errors.relation}</FieldError>
        </div>
      )}

      <div>
        <Field label="Age">
          <input
            className={inputClass}
            type="number"
            inputMode="numeric"
            min={0}
            max={120}
            value={draft.age}
            onChange={(e) => set('age', e.target.value)}
            aria-invalid={errors.age ? true : undefined}
          />
        </Field>
        <FieldError>{errors.age}</FieldError>
      </div>

      <Choices
        legend={variant === 'self' ? "Aangan's voice with you" : "Aangan's voice with them"}
        hint={variant === 'self' ? 'Aangan speaks to you in a female or male voice. You can change this later in Settings.' : 'Only matters if they talk to Aangan themselves.'}
        value={draft.gender}
        onChange={(g) => {
          setGenderTouched(true)
          set('gender', g)
        }}
        options={VOICE_OPTIONS}
        error={errors.gender}
      />

      {extras}

      {problem && (
        <p role="alert" className="rounded-md border border-l-4 border-line border-l-[var(--rw-danger)] bg-danger-bg px-3 py-2 text-sm font-medium">
          {problem}
        </p>
      )}

      <div className="flex flex-wrap justify-end gap-2 pt-1">
        {onCancel && (
          <Button variant="tertiary" onClick={onCancel} disabled={saving}>
            Cancel
          </Button>
        )}
        <Button type="submit" variant={submitVariant} loading={saving}>
          {saving ? 'Saving…' : label}
        </Button>
      </div>
    </form>
  )
}

/** A sheet that adds one person and closes itself when that worked. */
export function AddMemberSheet({ open, onClose, onAdded }: { open: boolean; onClose: () => void; onAdded?: (member: Member) => void }) {
  return (
    <Sheet open={open} title="Add someone to the family" onClose={onClose}>
      <MemberForm
        variant="other"
        onCancel={onClose}
        onDone={(m) => {
          onAdded?.(m)
          onClose()
        }}
      />
    </Sheet>
  )
}
