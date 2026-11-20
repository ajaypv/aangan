import { Loader2 } from 'lucide-react'
import type { ButtonHTMLAttributes, ElementType, HTMLAttributes, ReactNode } from 'react'
import { Tooltip as UiTooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { agentMeta, initials } from '@/lib/format'
import { cn } from '@/lib/utils'
import { colorFor, identityFor, identityOf } from '@/theme/identity'
import type { Member } from '@/types'

export { colorFor, identityFor, identityOf }

/* ------------------------------------------------------------------------------------------------------------------------------------
 * Identity: Avatar, MemberDots, AgentBadge
 * ---------------------------------------------------------------------------------------------------------------------------------- */

type AvatarMember = Pick<Member, 'name'> & { id?: string; color?: string }
export type Presence = 'online' | 'busy' | 'away'

const PRESENCE: Record<Presence, string> = {
  online: 'bg-[var(--rw-success)]',
  busy: 'bg-[var(--rw-danger)]',
  away: 'bg-[var(--rw-warning)]',
}

/** A member's initial on their identity colour (stable per person, from Redwood's data-visualisation palette). */
export function Avatar({
  member,
  size = 36,
  ring = false,
  presence,
  className,
}: {
  member: AvatarMember
  size?: number
  /** A brand ring marks the person currently speaking or selected. */
  ring?: boolean
  presence?: Presence
  className?: string
}) {
  const identity = identityOf(member)
  const dot = Math.max(8, Math.round(size * 0.28))
  return (
    <span aria-hidden="true" className={cn('relative inline-flex shrink-0', className)} style={{ width: size, height: size }}>
      <span
        className={cn('inline-flex size-full items-center justify-center rounded-full font-bold', ring && 'ring-2 ring-brand ring-offset-2 ring-offset-surface')}
        style={{ background: identity.color, color: identity.on, fontSize: size * 0.42 }}
      >
        {initials(member.name)}
      </span>
      {presence && <span className={cn('absolute bottom-0 right-0 rounded-full ring-2 ring-surface', PRESENCE[presence])} style={{ width: dot, height: dot }} />}
    </span>
  )
}

/** Dots for several members at once, e.g. on a shared calendar event. */
export function MemberDots({ members }: { members: AvatarMember[] }) {
  return (
    <span className="inline-flex -space-x-1" aria-label={members.map((m) => m.name).join(', ')} role="img">
      {members.map((m) => (
        <span key={m.id ?? m.name} className="size-2.5 rounded-full ring-2 ring-surface" style={{ background: identityOf(m).color }} />
      ))}
    </span>
  )
}

export function AgentBadge({ agent, className }: { agent: string | null | undefined; className?: string }) {
  const meta = agentMeta(agent)
  return (
    <span
      className={cn('inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-semibold text-ink', className)}
      style={{ background: `color-mix(in oklab, ${meta.color} 14%, var(--surface))` }}
    >
      <span className="size-2 rounded-full" style={{ background: meta.color }} aria-hidden="true" />
      {meta.label}
    </span>
  )
}

/* ------------------------------------------------------------------------------------------------------------------------------------
 * Status chips. Tone = a tint (step 20) behind text (step 120); every pair is at least 5:1. The old names (good, warn, bad) still work.
 * ---------------------------------------------------------------------------------------------------------------------------------- */

export type Tone = 'neutral' | 'brand' | 'success' | 'warning' | 'danger' | 'info' | 'good' | 'warn' | 'bad'

const TONES: Record<Exclude<Tone, 'good' | 'warn' | 'bad'>, string> = {
  neutral: 'bg-surface-2 text-ink-2',
  brand: 'bg-brand-soft text-brand-text',
  success: 'bg-success-bg text-[var(--rw-text-success)]',
  warning: 'bg-warning-bg text-[var(--rw-text-warning)]',
  danger: 'bg-danger-bg text-[var(--rw-text-danger)]',
  info: 'bg-info-bg text-info',
}
const ALIASES = { good: 'success', warn: 'warning', bad: 'danger' } as const

export function Pill({ tone = 'neutral', children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  const resolved = tone in ALIASES ? ALIASES[tone as keyof typeof ALIASES] : (tone as keyof typeof TONES)
  return <span className={cn('inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-semibold', TONES[resolved], className)}>{children}</span>
}
export const StatusChip = Pill

/** A small coloured dot that carries meaning in text next to it, never alone. */
export function StatusDot({ tone = 'neutral', className }: { tone?: Tone; className?: string }) {
  const color: Record<string, string> = {
    neutral: 'bg-[rgb(var(--rw-neutral-90))]',
    brand: 'bg-brand',
    success: 'bg-[var(--rw-success)]',
    good: 'bg-[var(--rw-success)]',
    warning: 'bg-[var(--rw-warning)]',
    warn: 'bg-[var(--rw-warning)]',
    danger: 'bg-[var(--rw-danger)]',
    bad: 'bg-[var(--rw-danger)]',
    info: 'bg-[var(--rw-info)]',
  }
  return <span aria-hidden="true" className={cn('inline-block size-2 shrink-0 rounded-full', color[tone], className)} />
}

/* ------------------------------------------------------------------------------------------------------------------------------------
 * Buttons: primary (filled brand), secondary (outlined neutral), tertiary (text), danger. 44px tall on phones, 36px with a pointer.
 * ---------------------------------------------------------------------------------------------------------------------------------- */

export type ButtonVariant = 'primary' | 'secondary' | 'tertiary' | 'danger'

const BUTTON_BASE =
  'inline-flex select-none items-center justify-center gap-2 rounded-md font-semibold transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-50'
const BUTTON_VARIANT: Record<ButtonVariant, string> = {
  primary: 'bg-brand text-brand-ink hover:bg-brand-hover active:bg-brand-hover',
  secondary: 'border border-edge bg-surface text-ink hover:bg-hover active:bg-[var(--active)]',
  tertiary: 'text-brand-text hover:bg-hover active:bg-[var(--active)]',
  danger: 'bg-[var(--rw-danger)] text-white hover:bg-[rgb(var(--rw-danger-130))] active:bg-[rgb(var(--rw-danger-140))]',
}
const BUTTON_SIZE = {
  md: 'min-h-11 px-4 text-base lg:min-h-9 lg:text-sm',
  sm: 'min-h-11 px-3 text-sm lg:min-h-8',
}

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  icon,
  className,
  children,
  disabled,
  type = 'button',
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; size?: keyof typeof BUTTON_SIZE; loading?: boolean; icon?: ReactNode }) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(BUTTON_BASE, BUTTON_VARIANT[variant], BUTTON_SIZE[size], className)}
      {...rest}
    >
      {loading ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : icon}
      {children}
    </button>
  )
}

/** An icon-only button. The label is required: it is the accessible name and the tooltip. */
export function IconButton({
  label,
  children,
  className,
  variant = 'tertiary',
  tooltip = true,
  ...rest
}: Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'aria-label'> & { label: string; variant?: 'tertiary' | 'secondary' | 'primary'; tooltip?: boolean }) {
  const button = (
    <button
      type="button"
      aria-label={label}
      className={cn(
        BUTTON_BASE,
        BUTTON_VARIANT[variant],
        'size-11 shrink-0 lg:size-9',
        variant === 'tertiary' && 'text-ink-2 hover:text-ink',
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  )
  return tooltip ? <Tooltip label={label}>{button}</Tooltip> : button
}

export function Tooltip({ label, children, side = 'top' }: { label: ReactNode; children: ReactNode; side?: 'top' | 'bottom' | 'left' | 'right' }) {
  return (
    <UiTooltip>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent side={side} sideOffset={6}>
        {label}
      </TooltipContent>
    </UiTooltip>
  )
}

/* ------------------------------------------------------------------------------------------------------------------------------------
 * Surfaces: Card, CardHeader / CardBody / CardFooter, ListCard + ListRow, SectionHeader, Section
 * ---------------------------------------------------------------------------------------------------------------------------------- */

/** White on the warm page, a 1px divider and the lightest Redwood shadow. */
export function Card({
  as,
  selected = false,
  className,
  children,
  ...rest
}: HTMLAttributes<HTMLElement> & { as?: ElementType; selected?: boolean }) {
  const Tag: ElementType = as ?? 'div'
  return (
    <Tag className={cn('rounded-xl border bg-surface shadow-xs', selected ? 'border-[var(--selected-edge)] bg-brand-soft' : 'border-line', className)} {...rest}>
      {children}
    </Tag>
  )
}

export function CardHeader({ title, subtitle, action, className }: { title: ReactNode; subtitle?: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <div className={cn('flex items-start justify-between gap-3 px-4 pt-4', className)}>
      <div className="min-w-0">
        <h3 className="t-card truncate">{title}</h3>
        {subtitle && <p className="t-secondary">{subtitle}</p>}
      </div>
      {action}
    </div>
  )
}
export const CardBody = ({ className, children }: { className?: string; children: ReactNode }) => <div className={cn('px-4 py-3', className)}>{children}</div>
export const CardFooter = ({ className, children }: { className?: string; children: ReactNode }) => (
  <div className={cn('flex flex-wrap items-center gap-2 border-t border-line px-4 py-3', className)}>{children}</div>
)

/** A card of rows separated by dividers. */
export function ListCard({ className, children, ...rest }: HTMLAttributes<HTMLUListElement>) {
  return (
    <ul className={cn('divide-y divide-line overflow-hidden rounded-xl border border-line bg-surface shadow-xs', className)} {...rest}>
      {children}
    </ul>
  )
}

/** One row: leading visual, title and subtitle, meta text and a trailing control. Pass onClick to make the whole row a button. */
export function ListRow({
  leading,
  title,
  subtitle,
  meta,
  trailing,
  selected = false,
  onClick,
  className,
}: {
  leading?: ReactNode
  title: ReactNode
  subtitle?: ReactNode
  meta?: ReactNode
  trailing?: ReactNode
  selected?: boolean
  onClick?: () => void
  className?: string
}) {
  const content = (
    <>
      {leading && <span className="flex shrink-0 items-center">{leading}</span>}
      <span className="min-w-0 flex-1">
        <span className="block truncate font-semibold">{title}</span>
        {subtitle && <span className="t-secondary block truncate">{subtitle}</span>}
      </span>
      {meta && <span className="num t-secondary shrink-0">{meta}</span>}
      {trailing && <span className="flex shrink-0 items-center gap-2">{trailing}</span>}
    </>
  )
  const row = cn('flex min-h-14 w-full items-center gap-3 px-4 py-2.5 text-left', selected && 'bg-brand-soft', className)
  return (
    <li>
      {onClick ? (
        <button type="button" onClick={onClick} className={cn(row, 'transition-colors hover:bg-hover')}>
          {content}
        </button>
      ) : (
        <div className={row}>{content}</div>
      )}
    </li>
  )
}

export function SectionHeader({
  title,
  hint,
  action,
  as: Heading = 'h2',
  className,
}: {
  title: string
  hint?: string
  action?: ReactNode
  as?: 'h2' | 'h3'
  className?: string
}) {
  return (
    <div className={cn('mb-3 flex items-end justify-between gap-3', className)}>
      <div className="min-w-0">
        <Heading className="t-section">{title}</Heading>
        {hint && <p className="t-secondary">{hint}</p>}
      </div>
      {action}
    </div>
  )
}

export function Section({ title, hint, action, children, className }: { title: string; hint?: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cn('mt-8 first:mt-0', className)}>
      <SectionHeader title={title} hint={hint} action={action} />
      {children}
    </section>
  )
}

/* ------------------------------------------------------------------------------------------------------------------------------------
 * Empty and loading states
 * ---------------------------------------------------------------------------------------------------------------------------------- */

export function EmptyState({ icon, title, children, action, className }: { icon?: ReactNode; title: string; children?: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <div className={cn('flex flex-col items-center gap-2 rounded-xl border border-line bg-surface px-6 py-8 text-center shadow-xs', className)}>
      {icon && <div className="mb-1 grid size-12 place-items-center rounded-full bg-surface-2 text-ink-2">{icon}</div>}
      <p className="t-card">{title}</p>
      {children && <div className="t-secondary max-w-sm">{children}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}
/** The name the screens already use. */
export const Empty = EmptyState

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('skeleton', className)} aria-hidden="true" />
}

export function ScreenSkeleton() {
  return (
    <div className="mx-auto max-w-5xl space-y-4 p-4 lg:p-8" role="status" aria-label="Loading…">
      <Skeleton className="h-8 w-56" />
      <Skeleton className="h-5 w-80 max-w-full" />
      <Skeleton className="h-40" />
      <div className="grid gap-4 md:grid-cols-2">
        <Skeleton className="h-52" />
        <Skeleton className="h-52" />
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------------------------------------------------------------------------
 * Forms: Field, inputClass, SegmentedControl, Switch
 * ---------------------------------------------------------------------------------------------------------------------------------- */

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-semibold">{label}</span>
      {children}
      {hint && <span className="t-caption mt-1 block">{hint}</span>}
    </label>
  )
}

export const inputClass =
  'min-h-11 w-full rounded-md border border-edge bg-surface px-3 py-2 text-base text-ink placeholder:text-ink-2 hover:border-[var(--rw-text-primary)] focus-visible:outline-2 focus-visible:outline-offset-0 lg:min-h-9 lg:text-sm'

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  label,
  className,
}: {
  options: { value: T; label: string; icon?: ReactNode }[]
  value: T
  onChange: (value: T) => void
  label: string
  className?: string
}) {
  return (
    <div role="radiogroup" aria-label={label} className={cn('inline-flex rounded-md border border-edge bg-surface p-0.5', className)}>
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
              'inline-flex min-h-10 items-center justify-center gap-1.5 rounded-[3px] px-3 text-sm font-semibold transition-colors lg:min-h-8',
              on ? 'bg-brand-soft text-brand-text' : 'text-ink-2 hover:bg-hover hover:text-ink',
            )}
          >
            {o.icon}
            {o.label}
          </button>
        )
      })}
    </div>
  )
}

export function Switch({ checked, onChange, label, disabled }: { checked: boolean; onChange: (next: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className="group inline-flex min-h-11 min-w-11 items-center justify-center disabled:cursor-not-allowed disabled:opacity-50 lg:min-h-9"
    >
      <span className={cn('relative h-6 w-11 rounded-full transition-colors', checked ? 'bg-brand' : 'bg-edge')}>
        <span className={cn('absolute top-0.5 size-5 rounded-full bg-white shadow-xs transition-[left]', checked ? 'left-[22px]' : 'left-0.5')} />
      </span>
    </button>
  )
}

/* ------------------------------------------------------------------------------------------------------------------------------------
 * Banner: a full-width notice with a coloured edge. Used for offline, update and install messages.
 * ---------------------------------------------------------------------------------------------------------------------------------- */

const BANNER: Record<'info' | 'success' | 'warning' | 'danger', string> = {
  info: 'border-l-[var(--rw-info)] bg-info-bg',
  success: 'border-l-[var(--rw-success)] bg-success-bg',
  warning: 'border-l-[var(--rw-warning)] bg-warning-bg',
  danger: 'border-l-[var(--rw-danger)] bg-danger-bg',
}

export function Banner({
  tone = 'info',
  icon,
  children,
  action,
  className,
}: {
  tone?: keyof typeof BANNER
  icon?: ReactNode
  children: ReactNode
  action?: ReactNode
  className?: string
}) {
  return (
    <div role="status" className={cn('flex items-center justify-between gap-3 border-b border-l-4 border-b-line px-4 py-2.5 text-sm', BANNER[tone], className)}>
      <span className="flex min-w-0 items-center gap-2 font-medium">
        {icon && <span className="shrink-0">{icon}</span>}
        <span>{children}</span>
      </span>
      {action && <span className="flex shrink-0 items-center gap-1">{action}</span>}
    </div>
  )
}
