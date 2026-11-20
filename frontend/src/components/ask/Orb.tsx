import { useEffect, useRef, type ReactNode } from 'react'
import { voice } from '@/lib/voiceSession'
import { cn } from '@/lib/utils'
import './orb.css'

export type OrbState = 'idle' | 'connecting' | 'listening' | 'thinking' | 'speaking' | 'muted'

/**
 * The calm centre of voice mode. `state` picks the look; `source` picks whose audio level makes the core swell (your microphone while you
 * talk, Aangan's voice while it speaks). The level is written straight to a CSS variable, so the app never re-renders for it.
 */
export function Orb({ state, source = 'none', size = 112, children, className }: { state: OrbState; source?: 'mic' | 'agent' | 'none'; size?: number; children?: ReactNode; className?: string }) {
  const el = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const node = el.current
    if (!node || source === 'none' || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      node?.style.setProperty('--lvl', '0')
      return
    }
    let raf = 0
    let smooth = 0
    const paint = () => {
      raf = requestAnimationFrame(paint)
      const levels = voice.getLevels()
      const raw = Math.min(1, (source === 'mic' ? levels.mic : levels.agent) * 2.4)
      smooth += (raw - smooth) * 0.35
      node.style.setProperty('--lvl', smooth.toFixed(3))
    }
    raf = requestAnimationFrame(paint)
    return () => cancelAnimationFrame(raf)
  }, [source])

  return (
    <div ref={el} className={cn('orb', className)} data-state={state} style={{ ['--orb-size' as string]: `${size}px` }} aria-hidden="true">
      <span className="orb__ring orb__ring--a" />
      <span className="orb__ring orb__ring--b" />
      <span className="orb__core">{children}</span>
    </div>
  )
}
