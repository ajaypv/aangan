import { dosesToday, factTone, factsOf, kidOf, nextEvents, schoolToday, seniorOf } from '@/lib/domain'
import { minutes } from '@/lib/format'
import { dayLabel } from '@/lib/format'
import type { Member, MemberArgs, MemberGender, MemberKind, MemberLanguage, Snapshot } from '@/types'

/* ------------------------------------------------------------------------------------------------------------------------------------
 * Who a person is, as the setup and edit forms collect it
 * ---------------------------------------------------------------------------------------------------------------------------------- */

export type Role = 'parent' | 'grandparent' | 'child' | 'other'

/** "I am a ...": the role picks the relation text stored for the person. */
export const ROLES: { value: Role; label: string; relation: string; hint: string }[] = [
  { value: 'parent', label: 'Parent', relation: 'Parent', hint: 'I look after the household' },
  { value: 'grandparent', label: 'Grandparent', relation: 'Grandparent', hint: 'I am an elder of the family' },
  { value: 'child', label: 'Child', relation: 'Child', hint: 'I am growing up here' },
  { value: 'other', label: 'Someone else', relation: 'Family', hint: 'A relative or a friend of the family' },
]

export const RELATION_SUGGESTIONS = ['Spouse', 'Son', 'Daughter', 'Mother', 'Father', 'Grandmother', 'Grandfather', 'Sister', 'Brother', 'Other']

export const DIET_OPTIONS = [
  { value: '', label: 'No restrictions' },
  { value: 'vegetarian', label: 'Vegetarian' },
  { value: 'vegan', label: 'Vegan' },
  { value: 'jain', label: 'Jain' },
]

export interface MemberDraft {
  name: string
  role: Role | ''
  relation: string
  /** Kept as typed so the field can be empty; validated into a number on submit. */
  age: string
  gender: MemberGender | ''
  allergies: string
  diet: string
  notes: string
  language: MemberLanguage
}

export const emptyDraft = (): MemberDraft => ({
  name: '',
  role: '',
  relation: '',
  age: '',
  gender: '',
  allergies: '',
  diet: '',
  notes: '',
  language: 'English',
})

/** The three forms share one draft: yourself (role and voice), someone else (relation), or editing a profile. */
export type FormVariant = 'self' | 'other' | 'edit'

export const firstName = (name: string) => name.trim().split(/\s+/)[0] ?? name

export const kindFromAge = (age: number): MemberKind => (age < 18 ? 'child' : age >= 60 ? 'senior' : 'adult')

const FEMALE_RELATIONS = ['mother', 'mom', 'mum', 'wife', 'daughter', 'sister', 'grandmother', 'aunt', 'niece']
const MALE_RELATIONS = ['father', 'dad', 'husband', 'son', 'brother', 'grandfather', 'uncle', 'nephew']

/** A best guess at gender from a relation word, used to preselect a voice. Empty when the word does not say. */
export function guessGender(relation: string): MemberGender | '' {
  const r = relation.trim().toLowerCase()
  if (FEMALE_RELATIONS.includes(r)) return 'female'
  if (MALE_RELATIONS.includes(r)) return 'male'
  return ''
}

export function memberToDraft(m: Member): MemberDraft {
  const gender = m.gender === 'female' || m.gender === 'male' ? m.gender : ''
  return { ...emptyDraft(), name: m.name, relation: m.relation, age: String(m.age), gender, language: (m.language as MemberLanguage) || 'English' }
}

export interface DraftErrors {
  name?: string
  age?: string
  relation?: string
  role?: string
  gender?: string
}

export function validateDraft(d: MemberDraft, variant: FormVariant): DraftErrors {
  const errors: DraftErrors = {}
  if (!d.name.trim()) errors.name = 'Enter a name.'
  else if (d.name.trim().length > 60) errors.name = 'Keep the name under 60 characters.'
  const age = Number(d.age)
  if (d.age.trim() === '') errors.age = 'Enter an age.'
  else if (!Number.isInteger(age) || age < 0 || age > 120) errors.age = 'Enter a whole number from 0 to 120.'
  if (variant === 'self' && !d.role) errors.role = 'Choose the option that fits you.'
  if ((variant === 'other' || variant === 'edit') && !d.relation.trim()) errors.relation = 'Say how they are related, for example Daughter.'
  if (variant === 'self' && !d.gender) errors.gender = 'Choose the voice you would like Aangan to use with you.'
  return errors
}

/** "peanuts, eggs and soy" becomes ["peanuts", "eggs", "soy"]. */
export function splitList(text: string): string[] {
  return text
    .split(/[,;\n]| and /i)
    .map((s) => s.trim())
    .filter(Boolean)
    .slice(0, 10)
}

/** Draft to the arguments the household tool takes. Assumes the draft passed validateDraft. */
export function draftToArgs(d: MemberDraft, variant: FormVariant): MemberArgs {
  const role = ROLES.find((r) => r.value === d.role)
  const args: MemberArgs = {
    name: d.name.trim(),
    relation: variant === 'self' ? (role?.relation ?? 'Family') : d.relation.trim(),
    age: Number(d.age),
    language: d.language,
  }
  if (d.gender) args.gender = d.gender
  const allergies = splitList(d.allergies)
  if (allergies.length) args.allergies = allergies
  if (d.diet) args.diet = [d.diet]
  if (d.notes.trim()) args.notes = d.notes.trim()
  return args
}

/* ------------------------------------------------------------------------------------------------------------------------------------
 * What the Family tab shows about a person
 * ---------------------------------------------------------------------------------------------------------------------------------- */

/** One calm line about where someone is right now, built from what Aangan already knows. */
export function statusLine(snap: Snapshot, m: Member): string {
  if (m.kind === 'child') {
    const kid = kidOf(snap, m.id)
    if (!kid) return 'No school updates yet'
    if (kid.status === 'at_school') return kid.arrived_at ? `At school since ${kid.arrived_at}` : 'At school'
    const start = schoolToday(snap, m.id)?.start
    return start !== undefined && minutes(snap.now.time) > minutes(start) ? 'Not at school yet' : 'No school updates yet'
  }
  if (m.kind === 'senior') {
    const senior = seniorOf(snap, m.id)
    if (!senior || senior.meds.length === 0) return 'No medicines added yet'
    const low = senior.meds.filter((med) => med.stock_days <= 3).sort((a, b) => a.stock_days - b.stock_days)[0]
    if (low) return `${low.name} has ${low.stock_days} ${low.stock_days === 1 ? 'day' : 'days'} left`
    const doses = dosesToday(snap, senior)
    if (doses.some((d) => d.status === 'missed')) return 'A dose is overdue'
    if (doses.some((d) => d.status === 'due')) return 'A dose is due now'
    const next = doses.find((d) => d.status === 'upcoming')
    return next ? `Next dose at ${next.slot}` : 'All doses taken today'
  }
  const next = nextEvents(snap, m.id, 1)[0]
  return next ? `Next: ${next.title}, ${dayLabel(next.date)} at ${next.start}` : 'Nothing scheduled'
}

export interface MemberChip {
  text: string
  tone: 'danger' | 'warning' | 'neutral'
}

/** Allergies first, then access and health needs, then food habits. */
export function memberChips(snap: Snapshot, m: Member): MemberChip[] {
  const toneOf = { bad: 'danger', warn: 'warning', neutral: 'neutral' } as const
  const rank = { danger: 0, warning: 1, neutral: 2 } as const
  return factsOf(snap, m.id)
    .map((f) => ({ text: f.fact, tone: toneOf[factTone(f)] }))
    .sort((a, b) => rank[a.tone] - rank[b.tone])
}

/* ------------------------------------------------------------------------------------------------------------------------------------
 * Tailored example prompts for the "all set" step
 * ---------------------------------------------------------------------------------------------------------------------------------- */

export function examplePrompts(members: Member[]): string[] {
  const child = members.find((m) => m.kind === 'child')
  const senior = members.find((m) => m.kind === 'senior')
  const prompts = [
    members.length > 1 ? "Let's all go out for lunch on Sunday" : "What's on my schedule tomorrow?",
    child ? `How is ${firstName(child.name)} doing in school?` : members.length > 1 ? 'When is everyone free on Sunday?' : 'Book a table for dinner tonight',
    senior ? `Did ${firstName(senior.name)} take their medicines today?` : 'How much did we spend this month?',
    'I spent 450 on groceries',
  ]
  return [...new Set(prompts)].slice(0, 3)
}

/* ------------------------------------------------------------------------------------------------------------------------------------
 * Setup progress: remembered for this browser tab only, so a reload in the middle of the wizard resumes instead of restarting
 * ---------------------------------------------------------------------------------------------------------------------------------- */

const SETUP_KEY = 'aangan.setup'

export interface SetupProgress {
  step: 'family' | 'done'
  /** The id of the person who set the household up (the first profile created). */
  firstId: string
}

export function loadSetup(): SetupProgress | null {
  try {
    const raw = sessionStorage.getItem(SETUP_KEY)
    if (!raw) return null
    const v = JSON.parse(raw) as Partial<SetupProgress>
    return (v.step === 'family' || v.step === 'done') && typeof v.firstId === 'string' ? { step: v.step, firstId: v.firstId } : null
  } catch {
    return null
  }
}

export function saveSetup(progress: SetupProgress): void {
  try {
    sessionStorage.setItem(SETUP_KEY, JSON.stringify(progress))
  } catch {
    // Not persisted: a reload simply starts the wizard from the profile picker.
  }
}

export function clearSetup(): void {
  try {
    sessionStorage.removeItem(SETUP_KEY)
  } catch {
    // Nothing to clear.
  }
}
