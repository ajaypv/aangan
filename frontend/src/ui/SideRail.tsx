import { useApp } from '@/state/AppState'
import { cn } from '@/lib/utils'
import { NAV_ITEMS, navLink } from './BottomNav'
import { ConnectionDot, LiveControls, UserMenu, Wordmark } from './Brand'

/** Desktop navigation (1024px and wider): the wordmark with the connection dot, the same four places, and the signed-in person. */
export function SideRail() {
  const { tab, setTab, snap } = useApp()
  const waiting = snap?.pending ? 1 : 0
  return (
    <aside className="hidden w-64 shrink-0 flex-col gap-8 overflow-y-auto border-r border-line bg-surface px-3 py-6 lg:flex">
      <div className="flex items-center justify-between px-3">
        <Wordmark />
        <ConnectionDot />
      </div>

      <nav aria-label="Main">
        <ul className="space-y-1">
          {NAV_ITEMS.map(({ id, label, icon: Icon }) => {
            const active = id === tab
            const ask = id === 'ask'
            return (
              <li key={id}>
                <a
                  {...navLink(id, setTab)}
                  aria-current={active ? 'page' : undefined}
                  className={cn(
                    'relative flex w-full items-center gap-3 rounded-md px-3 text-left text-sm transition-colors',
                    ask ? 'min-h-12' : 'min-h-10',
                    active ? 'bg-brand-soft font-bold text-brand-text' : ask ? 'font-bold text-brand-text hover:bg-brand-soft' : 'font-medium text-ink hover:bg-hover',
                  )}
                >
                  {active && <span aria-hidden="true" className="absolute inset-y-1.5 left-0 w-[3px] rounded-r-sm bg-brand" />}
                  {ask ? (
                    <span className="grid size-8 place-items-center rounded-full bg-brand text-brand-ink" aria-hidden="true">
                      <Icon className="size-[18px]" strokeWidth={2.2} />
                    </span>
                  ) : (
                    <Icon className="size-5" strokeWidth={active ? 2.4 : 2} aria-hidden="true" />
                  )}
                  {label}
                  {ask && waiting > 0 && <span className="ml-auto rounded-md bg-warning-bg px-1.5 py-0.5 text-xs font-bold text-[var(--rw-text-warning)]">Reply needed</span>}
                </a>
              </li>
            )
          })}
        </ul>
      </nav>

      <div className="mt-auto space-y-3 px-1">
        <LiveControls />
        <UserMenu showName align="start" side="top" />
      </div>
    </aside>
  )
}
