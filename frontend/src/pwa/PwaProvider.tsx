import { createContext, useContext, type ReactNode } from 'react'
import { usePwaState, type PwaState } from './usePwa'

const PwaContext = createContext<PwaState | null>(null)

/** One install and update state for the whole app, so the banner and Settings agree and the service worker registers once. */
export function PwaProvider({ children }: { children: ReactNode }) {
  const state = usePwaState()
  return <PwaContext.Provider value={state}>{children}</PwaContext.Provider>
}

export function usePwa(): PwaState {
  const state = useContext(PwaContext)
  if (!state) throw new Error('usePwa must be used inside PwaProvider')
  return state
}
