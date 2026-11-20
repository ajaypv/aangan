import { Check } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useApp } from '@/state/AppState'
import { cn } from '@/lib/utils'
import type { Stage } from '@/types'

const STAGES: { id: Stage; label: string }[] = [
  { id: 'before', label: 'Before' },
  { id: 'during', label: 'During' },
  { id: 'action', label: 'Action' },
  { id: 'after', label: 'After' },
]

const LINGER_MS = 4000

/**
 * Where the current request is (Before, During, Action, After). It floats over the top of the page only while a request is being
 * handled or has just moved on, and disappears again, so it never takes up room the rest of the time.
 */
export function ProgressStrip({ className }: { className?: string }) {
  const { snap, busy } = useApp()
  const signal = snap ? `${snap.stage}|${snap.events.length}|${snap.transcript.length}` : ''
  const seen = useRef(signal)
  const [recent, setRecent] = useState(false)

  useEffect(() => {
    // Only a change counts: mounting, or React re-running this effect, must not make the strip appear.
    if (!signal || signal === seen.current) return
    seen.current = signal
    setRecent(true)
    const id = window.setTimeout(() => setRecent(false), LINGER_MS)
    return () => window.clearTimeout(id)
  }, [signal])

  if (!snap || !(busy || recent)) return null
  const at = STAGES.findIndex((s) => s.id === snap.stage)
  return (
    <div className={cn('pointer-events-none absolute inset-x-0 top-3 z-20 flex justify-center px-4', className)} role="status" aria-live="polite">
      <ol aria-label="Where the current request is" className="rise pointer-events-auto flex items-center gap-1 rounded-lg border border-line bg-surface p-1 text-xs shadow-md">
        {STAGES.map((s, i) => {
          const current = i === at
          const done = i < at
          return (
            <li
              key={s.id}
              aria-current={current ? 'step' : undefined}
              className={cn(
                'inline-flex items-center gap-1 rounded-md px-2.5 py-1 font-semibold',
                current ? 'bg-brand text-brand-ink' : done ? 'bg-brand-soft text-brand-text' : 'text-ink-2',
              )}
            >
              {done && <Check className="size-3" aria-hidden="true" />}
              {s.label}
            </li>
          )
        })}
      </ol>
    </div>
  )
}
