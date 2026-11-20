import { Home, Settings, Sparkles, Users, type LucideIcon } from 'lucide-react'
import { useApp, type Tab } from '@/state/AppState'
import { cn } from '@/lib/utils'

/** Four places, all equal in the bar. Ask is the assistant and sits second, with its sparkle icon in line with the rest. */
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

/**
 * Phone navigation, the standard bottom bar: four equal items, each an icon over a label, the current one with its icon in a soft pill.
 * Nothing floats above the bar, so it never covers the content or the message box. The desktop rail replaces it from 1024px.
 */
export function BottomNav() {
  const { tab, setTab, snap } = useApp()
  const waiting = snap?.pending ? 1 : 0
  return (
    <nav aria-label="Main" className="relative z-10 border-t border-line bg-surface pb-[env(safe-area-inset-bottom)] lg:hidden">
      <ul className="mx-auto grid max-w-md grid-cols-4">
        {NAV_ITEMS.map(({ id, label, icon: Icon }) => {
          const active = id === tab
          return (
            <li key={id}>
              <a
                {...navLink(id, setTab)}
                aria-current={active ? 'page' : undefined}
                className={cn(
                  'flex min-h-16 w-full flex-col items-center justify-center gap-1 pb-1 pt-2 text-xs transition-colors short:min-h-12 short:pt-1',
                  active ? 'font-bold text-brand-text' : 'font-medium text-ink-2',
                )}
              >
                <span
                  className={cn(
                    'relative grid h-8 w-16 place-items-center rounded-full transition-colors short:h-7',
                    active ? 'bg-brand-soft' : 'active:bg-hover',
                  )}
                >
                  <Icon className="size-[22px]" strokeWidth={active ? 2.4 : 2} aria-hidden="true" />
                  {id === 'ask' && waiting > 0 && (
                    <span
                      className="absolute right-3 top-0.5 size-2.5 rounded-full bg-[var(--rw-warning)] ring-2 ring-surface"
                      role="img"
                      aria-label="Waiting for your answer"
                    />
                  )}
                </span>
                <span className="short:sr-only">{label}</span>
              </a>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
