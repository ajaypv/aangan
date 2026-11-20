import { useEffect, useRef, type ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { BrandMark } from '@/ui/Brand'

/** The page frame every setup screen shares: one centred column, generous space, the mark on top. */
export function Frame({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto flex min-h-full w-full max-w-md flex-col gap-6 px-5 py-8 pb-[max(2rem,env(safe-area-inset-bottom))] lg:py-14">
      <BrandMark size={44} />
      {children}
    </div>
  )
}

/** The screen title. It takes focus when the screen appears so keyboard and screen-reader users start at the top. */
export function ScreenHeading({ title, children }: { title: string; children?: ReactNode }) {
  const ref = useRef<HTMLHeadingElement>(null)
  useEffect(() => ref.current?.focus({ preventScroll: true }), [])
  return (
    <div>
      <h1 ref={ref} tabIndex={-1} className="t-page outline-none">
        {title}
      </h1>
      {children && <p className="t-secondary mt-1">{children}</p>}
    </div>
  )
}

/** Three short bars with a text label, so progress is never colour-only. */
export function Progress({ step, total = 3 }: { step: number; total?: number }) {
  return (
    <div role="progressbar" aria-valuemin={1} aria-valuemax={total} aria-valuenow={step} aria-label={`Step ${step} of ${total}`}>
      <div className="flex gap-1.5" aria-hidden="true">
        {Array.from({ length: total }, (_, i) => (
          <span key={i} className={cn('h-1 flex-1 rounded-full', i < step ? 'bg-brand' : 'bg-[rgb(var(--rw-neutral-40))]')} />
        ))}
      </div>
      <p className="t-caption mt-1.5">
        Step {step} of {total}
      </p>
    </div>
  )
}
