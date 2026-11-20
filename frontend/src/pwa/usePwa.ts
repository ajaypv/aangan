import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { registerSW } from 'virtual:pwa-register'

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

/*
 * The browser fires `beforeinstallprompt` once, early. It is caught here, when this file is first imported, so it is never missed because
 * a screen had not mounted yet, and every screen (the banner, Settings) sees the same event.
 */
let deferred: BeforeInstallPromptEvent | null = null
let installed = false
const listeners = new Set<() => void>()
const emit = () => listeners.forEach((l) => l())
const subscribe = (l: () => void) => {
  listeners.add(l)
  return () => {
    listeners.delete(l)
  }
}

if (typeof window !== 'undefined') {
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault()
    deferred = e as BeforeInstallPromptEvent
    emit()
  })
  window.addEventListener('appinstalled', () => {
    deferred = null
    installed = true
    emit()
  })
}

const standalone = () =>
  window.matchMedia('(display-mode: standalone)').matches || (navigator as Navigator & { standalone?: boolean }).standalone === true

/** Where the person is, so the install help can say the right thing for their device. */
export type InstallPlatform = 'ios' | 'android' | 'desktop'
const platform = (): InstallPlatform => {
  const ua = navigator.userAgent
  if (/iphone|ipad|ipod/i.test(ua)) return 'ios'
  if (/android/i.test(ua)) return 'android'
  return 'desktop'
}

/** The state behind the app's install, update and offline notices. Use usePwa() inside the app; this runs once, in PwaProvider. */
export function usePwaState() {
  const installEvent = useSyncExternalStore(subscribe, () => deferred, () => null)
  const wasInstalled = useSyncExternalStore(subscribe, () => installed, () => false)
  const [updateReady, setUpdateReady] = useState(false)
  const [offlineReady, setOfflineReady] = useState(false)
  const updateSW = useRef<((reload?: boolean) => Promise<void>) | null>(null)

  useEffect(() => {
    updateSW.current = registerSW({
      onNeedRefresh: () => setUpdateReady(true),
      onOfflineReady: () => setOfflineReady(true),
    })
  }, [])

  const install = useCallback(async () => {
    const event = deferred
    if (!event) return
    await event.prompt()
    await event.userChoice
    deferred = null
    emit()
  }, [])

  const applyUpdate = useCallback(() => void updateSW.current?.(true), [])
  const dismissUpdate = useCallback(() => setUpdateReady(false), [])
  const dismissOfflineReady = useCallback(() => setOfflineReady(false), [])

  const where = platform()
  const isInstalled = wasInstalled || standalone()

  return {
    /** The browser is ready to show its own install dialog: one tap installs. */
    canInstall: installEvent !== null && !isInstalled,
    install,
    /** Already running as an installed app. */
    isInstalled,
    platform: where,
    /** iOS has no install prompt; the person must use Share, then Add to Home Screen. */
    showIosHint: where === 'ios' && !isInstalled,
    updateReady,
    applyUpdate,
    dismissUpdate,
    offlineReady,
    dismissOfflineReady,
  }
}

export type PwaState = ReturnType<typeof usePwaState>
