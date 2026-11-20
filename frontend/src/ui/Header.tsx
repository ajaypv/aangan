import { useApp } from '@/state/AppState'
import { ConnectionDot, LiveControls, UserMenu, Wordmark } from './Brand'

/** The phone top bar: wordmark, a connection dot, and the signed-in person's avatar menu. From 1024px the side rail carries all of this. */
export function Header() {
  const { snap } = useApp()
  if (!snap) return null
  return (
    <header className="flex items-center justify-between gap-3 border-b border-line bg-surface px-4 pb-2 pt-[max(0.5rem,env(safe-area-inset-top))] lg:hidden">
      <div className="flex items-center gap-1.5">
        <Wordmark />
        <ConnectionDot />
      </div>
      <div className="flex items-center gap-2">
        <LiveControls />
        <UserMenu />
      </div>
    </header>
  )
}
