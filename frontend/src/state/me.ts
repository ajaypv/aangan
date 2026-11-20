import { useSyncExternalStore } from 'react'

/**
 * Who is using this device: a family member's id in localStorage under `aangan.me`, and `aangan.onboarded` once setup has been done.
 * Storage can be blocked (private mode, strict settings), so every access is guarded and an in-memory copy keeps the choice for the
 * session. Changes made in this tab and in other tabs both reach every `useMe()` caller.
 */
export const ME_KEY = 'aangan.me'
export const ONBOARDED_KEY = 'aangan.onboarded'
const CHANGED = 'aangan:me-changed'

const memory = new Map<string, string>()

function read(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return memory.get(key) ?? null
  }
}

function write(key: string, value: string | null) {
  try {
    if (value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, value)
  } catch {
    if (value === null) memory.delete(key)
    else memory.set(key, value)
  }
  window.dispatchEvent(new Event(CHANGED))
}

export const getMe = (): string | null => read(ME_KEY)
export const setMe = (memberId: string): void => write(ME_KEY, memberId)
export const clearMe = (): void => write(ME_KEY, null)

export const isOnboarded = (): boolean => read(ONBOARDED_KEY) === '1'
export const markOnboarded = (): void => write(ONBOARDED_KEY, '1')
export const clearOnboarded = (): void => write(ONBOARDED_KEY, null)

function subscribe(onChange: () => void) {
  window.addEventListener('storage', onChange) // other tabs
  window.addEventListener(CHANGED, onChange) // this tab
  return () => {
    window.removeEventListener('storage', onChange)
    window.removeEventListener(CHANGED, onChange)
  }
}

export function useMe() {
  const me = useSyncExternalStore(subscribe, getMe, () => null)
  const onboarded = useSyncExternalStore(subscribe, isOnboarded, () => false)
  return { me, onboarded, setMe, clearMe, markOnboarded, clearOnboarded }
}
