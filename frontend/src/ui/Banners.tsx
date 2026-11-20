import { CheckCircle2, Download, Info, WifiOff, X, XCircle } from 'lucide-react'
import { useState } from 'react'
import { useApp } from '@/state/AppState'
import { usePwa } from '@/pwa/PwaProvider'
import { cn } from '@/lib/utils'
import { Banner, Button, IconButton } from './primitives'

const DISMISSED = 'aangan-install-dismissed'
const SNOOZE_MS = 7 * 24 * 60 * 60 * 1000 // "Not now" hides the install offer for a week; Settings always has it

const TOAST_EDGE = {
  success: 'border-l-[var(--rw-success)]',
  error: 'border-l-[var(--rw-danger)]',
  info: 'border-l-[var(--rw-info)]',
}

/** Redwood message: a white card with a coloured left edge and the middle shadow. Errors are announced at once, the rest politely. */
export function Toasts() {
  const { toasts, dismissToast } = useApp()
  return (
    <div className="pointer-events-none fixed inset-x-0 top-[max(0.75rem,env(safe-area-inset-top))] z-50 mx-auto flex w-full max-w-md flex-col gap-2 px-3" aria-live="polite">
      {toasts.map((t) => (
        <div
          key={t.id}
          role={t.kind === 'error' ? 'alert' : 'status'}
          className={cn('rise pointer-events-auto flex items-start gap-3 rounded-lg border border-l-4 border-line bg-surface py-2.5 pl-3.5 pr-1.5 text-sm text-ink shadow-md', TOAST_EDGE[t.kind])}
        >
          {t.kind === 'success' && <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-[var(--rw-text-success)]" aria-hidden="true" />}
          {t.kind === 'error' && <XCircle className="mt-0.5 size-5 shrink-0 text-[var(--rw-text-danger)]" aria-hidden="true" />}
          {t.kind === 'info' && <Info className="mt-0.5 size-5 shrink-0 text-info" aria-hidden="true" />}
          <p className="flex-1 self-center font-medium">{t.text}</p>
          <IconButton label="Dismiss" tooltip={false} className="-my-1 size-9 lg:size-8" onClick={() => dismissToast(t.id)}>
            <X className="size-4" />
          </IconButton>
        </div>
      ))}
    </div>
  )
}

const DEMO_DISMISSED = 'aangan.demo-banner-dismissed'

/** Shown only while the family on screen is the built-in demo family. A real household never sees it. */
export function DemoBanner() {
  const { household, reset, busy } = useApp()
  const [armed, setArmed] = useState(false)
  const [hidden, setHidden] = useState(() => {
    try {
      return sessionStorage.getItem(DEMO_DISMISSED) === '1'
    } catch {
      return false
    }
  })
  if (!household.demo || hidden) return null
  // Reset replaces everything on screen with the starting family, so it takes a second press; it relaxes again after a few seconds.
  const onReset = () => {
    if (!armed) {
      setArmed(true)
      window.setTimeout(() => setArmed(false), 4000)
      return
    }
    setArmed(false)
    void reset()
  }
  const dismiss = () => {
    setHidden(true)
    try {
      sessionStorage.setItem(DEMO_DISMISSED, '1')
    } catch {
      // Not persisted.
    }
  }
  return (
    <Banner
      tone="info"
      action={
        <>
          <Button size="sm" variant={armed ? 'danger' : 'tertiary'} loading={busy} onClick={onReset}>
            {armed ? 'Press again to reset' : 'Reset'}
          </Button>
          <IconButton label="Dismiss" tooltip={false} className="size-9 lg:size-8" onClick={dismiss}>
            <X className="size-4" />
          </IconButton>
        </>
      }
    >
      Demo family. These are example people, not your own.
    </Banner>
  )
}

export function StatusBanners() {
  const { online } = useApp()
  const pwa = usePwa()
  const [hidden, setHidden] = useState(() => {
    try {
      const until = Number(localStorage.getItem(DISMISSED))
      return Number.isFinite(until) && until > Date.now()
    } catch {
      return false
    }
  })
  const hideInstall = () => {
    setHidden(true)
    try {
      localStorage.setItem(DISMISSED, String(Date.now() + SNOOZE_MS))
    } catch {
      // Not persisted.
    }
  }

  return (
    <>
      {!online && (
        <Banner tone="warning" icon={<WifiOff className="size-4" aria-hidden="true" />}>
          You are offline. Aangan can open, but it needs a connection to reach your family's assistant.
        </Banner>
      )}
      {pwa.updateReady && (
        <Banner
          tone="info"
          action={
            <>
              <Button size="sm" onClick={pwa.applyUpdate}>
                Update
              </Button>
              <Button size="sm" variant="tertiary" onClick={pwa.dismissUpdate}>
                Later
              </Button>
            </>
          }
        >
          A new version of Aangan is ready.
        </Banner>
      )}
      {pwa.offlineReady && !pwa.updateReady && (
        <Banner
          tone="success"
          action={
            <Button size="sm" variant="tertiary" onClick={pwa.dismissOfflineReady}>
              OK
            </Button>
          }
        >
          Aangan is ready to open offline.
        </Banner>
      )}
      {!hidden && (pwa.canInstall || pwa.showIosHint) && (
        <Banner
          tone="info"
          icon={<Download className="size-4" aria-hidden="true" />}
          action={
            <>
              {pwa.canInstall && (
                <Button size="sm" onClick={() => void pwa.install()}>
                  Install
                </Button>
              )}
              <Button size="sm" variant="tertiary" onClick={hideInstall}>
                Not now
              </Button>
            </>
          }
        >
          {pwa.canInstall ? 'Install Aangan on this device.' : 'To install: tap Share, then Add to Home Screen.'}
        </Banner>
      )}
    </>
  )
}
