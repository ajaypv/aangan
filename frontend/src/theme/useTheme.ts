import { useEffect } from 'react'

/**
 * Aangan uses Oracle's Redwood light theme only. The hook keeps its old shape so screens that still import it keep compiling,
 * but every preference resolves to light, and it makes sure the page and the browser bar are light.
 */
export type ThemePref = 'system' | 'light' | 'dark'

const BAR = '#fbf9f8' // --rw-neutral-10

function applyLight() {
  document.documentElement.dataset.theme = 'light'
  for (const meta of document.querySelectorAll('meta[name="theme-color"]')) meta.setAttribute('content', BAR)
}

export function useTheme() {
  useEffect(applyLight, [])
  return { pref: 'light' as ThemePref, setPref: (_next: ThemePref) => {} }
}
