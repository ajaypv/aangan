import { Home, Settings, Sparkles, Users, type LucideIcon } from 'lucide-react'
import { useApp, type Tab } from '@/state/AppState'
import { cn } from '@/lib/utils'

/** Four places. Ask is the assistant and the heart of the app, so it is the one that stands out. */
export const NAV_ITEMS: { id: Tab; label: string; icon: LucideIcon }[] = [
  { id: 'home', label: 'Home', icon: Home },
  { id: 'ask', label: 'Ask', icon: Sparkles },
  { id: 'family', label: 'Family', icon: Users },
  { id: 'settings', label: 'Settings', icon: Settings },
]

/**
 * The props that make a navigation item a real link: it has an address (so Ctrl or Cmd click, middle click and "copy link" work), and a
 * plain click switches place without reloading the page.
 */
export function navLink(id: Tab, setTab: (t: Tab) => void) {
  return {
    href: `?tab=${id}`,
    onClick: (e: React.MouseEvent) => {
      if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
      e.preventDefault()
      setTab(id)
    },
  }
}

/** Phone navigation: four items with Ask as a raised brand button. The desktop rail replaces it from 1024px. */
export function BottomNav() {
  const { tab, setTab, snap } = useApp()
  const waiting = snap?.pending ? 1 : 0
  return (
    <nav aria-label="Main" className="relative z-10 border-t border-line bg-surface pb-[env(safe-area-inset-bottom)] lg:hidden">
      <ul className="mx-auto grid max-w-md grid-cols-4">
        {NAV_ITEMS.map(({ id, label, icon: Icon }) => {
          const active = id === tab
          if (id === 'ask') {
            return (
              <li key={id}>
                <a
                  {...navLink(id, setTab)}
                  aria-current={active ? 'page' : undefined}
                  className="relative flex min-h-14 w-full flex-col items-center justify-end gap-0.5 pb-1.5 text-xs font-bold text-brand-text short:min-h-11"
                >
                  <span
                    className={cn(
                      '-mt-7 grid size-14 place-items-center rounded-full bg-brand text-brand-ink shadow-md ring-4 ring-surface transition-colors short:-mt-4 short:size-11',
                      active ? 'bg-brand-hover' : 'active:bg-brand-hover',
                    )}
                  >
                    <Icon className="size-6 short:size-5" strokeWidth={2.2} />
                    {waiting > 0 && <span className="absolute right-0 top-0 size-3.5 rounded-full bg-[var(--rw-warning)] ring-2 ring-surface" role="img" aria-label="Waiting for your answer" />}
                  </span>
                  <span className="short:sr-only">{label}</span>
                </a>
              </li>
            )
          }
          return (
            <li key={id}>
              <a
                {...navLink(id, setTab)}
                aria-current={active ? 'page' : undefined}
                className={cn(
                  'relative flex min-h-14 w-full flex-col items-center justify-center gap-0.5 text-xs transition-colors short:min-h-11',
                  active ? 'font-bold text-brand-text' : 'font-medium text-ink-2 active:bg-hover',
                )}
              >
                {active && <span aria-hidden="true" className="absolute inset-x-5 top-0 h-[3px] rounded-b-sm bg-brand" />}
                <Icon className="size-[22px]" strokeWidth={active ? 2.4 : 2} aria-hidden="true" />
                <span className="short:sr-only">{label}</span>
              </a>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
