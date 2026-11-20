import { CloudOff } from 'lucide-react'
import { TooltipProvider } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { PwaProvider } from '@/pwa/PwaProvider'
import { Home } from '@/screens/Home'
import { Onboarding } from '@/screens/Onboarding'
import { SettingsScreen } from '@/screens/SettingsScreen'
import { AppProvider, useApp, type Tab } from '@/state/AppState'
import { DemoBanner, StatusBanners, Toasts } from '@/ui/Banners'
import { BottomNav } from '@/ui/BottomNav'
import { Header } from '@/ui/Header'
import { Button, EmptyState, ScreenSkeleton } from '@/ui/primitives'
import { SideRail } from '@/ui/SideRail'
import { AskTab, FamilyTab } from '@/ui/TabViews'
import { useTheme } from '@/theme/useTheme'

const SCREENS: Record<Tab, () => React.ReactNode> = {
  home: () => <Home />,
  ask: () => <AskTab />,
  family: () => <FamilyTab />,
  settings: () => <SettingsScreen />,
}

function Shell() {
  const { snap, loading, loadError, tab, reload, personaId, household } = useApp()
  useTheme()

  if (!snap) {
    return (
      <div className="h-dvh overflow-y-auto bg-bg text-ink">
        {loading ? (
          <ScreenSkeleton />
        ) : (
          <div className="mx-auto max-w-md p-6">
            <EmptyState
              icon={<CloudOff className="size-6" aria-hidden="true" />}
              title="Aangan cannot reach its server"
              action={<Button onClick={reload}>Try again</Button>}
            >
              <p>{loadError}</p>
            </EmptyState>
          </div>
        )}
        <Toasts />
      </div>
    )
  }

  // No household yet, or nobody has chosen who is using this device: the setup screens come first, with no navigation around them.
  if (!household.exists || snap.members.length === 0 || !personaId) {
    return (
      <div className="h-dvh overflow-y-auto bg-bg text-ink">
        <Onboarding />
        <Toasts />
      </div>
    )
  }

  return (
    <div className="flex h-dvh bg-bg text-ink">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-brand focus:px-3 focus:py-2 focus:text-brand-ink"
      >
        Skip to content
      </a>
      <SideRail />
      <div className="flex min-w-0 flex-1 flex-col">
        <DemoBanner />
        <StatusBanners />
        <Header />
        <main id="main" className={cn('min-h-0 flex-1', tab === 'ask' ? 'overflow-hidden' : 'overflow-y-auto')}>
          <div key={tab} className="rise h-full">
            {SCREENS[tab]()}
          </div>
        </main>
        <BottomNav />
      </div>
      <Toasts />
    </div>
  )
}

export default function App() {
  return (
    <TooltipProvider>
      <PwaProvider>
        <AppProvider>
          <Shell />
        </AppProvider>
      </PwaProvider>
    </TooltipProvider>
  )
}
