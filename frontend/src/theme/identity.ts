/**
 * Identity colours: one stable hue per family member (and per agent in index.css), taken from Redwood's data-visualisation palette.
 * `on` is the initial's colour, chosen so the pair meets WCAG AA (4.5:1): the lighter hues take dark ink, the darker ones white.
 */
export interface Identity {
  /** CSS colour, from --rw-dvt-* */
  color: string
  /** Colour for text or an initial drawn on `color` */
  on: string
}

const WHITE = 'rgb(var(--rw-neutral-0))'
const DARK = 'rgb(var(--rw-neutral-190))'
const dvt = (n: number) => `rgb(var(--rw-dvt-${n}))`

const PALETTE: Identity[] = [
  { color: dvt(2), on: DARK }, // orange
  { color: dvt(1), on: WHITE }, // deep teal
  { color: dvt(5), on: DARK }, // green
  { color: dvt(10), on: WHITE }, // plum
  { color: dvt(8), on: DARK }, // lavender
  { color: dvt(6), on: DARK }, // rose
  { color: dvt(3), on: DARK }, // teal
  { color: dvt(7), on: WHITE }, // rust
]

/** The seeded family keeps four clearly different colours; anyone added later gets a stable pick from the rest. */
const KNOWN: Record<string, number> = { priya: 0, rahul: 1, aarav: 2, dadi: 3 }

const hash = (s: string) => {
  let h = 0
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0
  return h
}

const HEX = /^#([0-9a-f]{6})$/i

function luminance(hex: string) {
  const channel = (i: number) => {
    const v = parseInt(hex.slice(1 + i * 2, 3 + i * 2), 16) / 255
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * channel(0) + 0.7152 * channel(1) + 0.0722 * channel(2)
}

/** White or near-black, whichever reads better (at least 4.5:1 for every Redwood data-visualisation colour) on a hex background. */
export function onColor(hex: string): string {
  const l = luminance(hex)
  const withWhite = 1.05 / (l + 0.05)
  const withDark = (l + 0.05) / (luminance('#161513') + 0.05)
  return withWhite >= withDark ? WHITE : DARK
}

/**
 * A member's identity. The backend gives each person a Redwood data-visualisation colour (`color`); use it so every screen agrees,
 * and fall back to a stable pick for anyone without one.
 */
export function identityOf(member: { id?: string; name: string; color?: string }): Identity {
  if (member.color && HEX.test(member.color)) return { color: member.color, on: onColor(member.color) }
  return identityFor(member.id ?? member.name)
}

export function identityFor(key: string): Identity {
  const known = KNOWN[key.toLowerCase()]
  if (known !== undefined) return PALETTE[known]
  return PALETTE[4 + (hash(key.toLowerCase()) % (PALETTE.length - 4))]
}

export const colorFor = (key: string) => identityFor(key).color
