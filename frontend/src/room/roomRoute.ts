import { useSyncExternalStore } from 'react'

/**
 * The room address: `?room=<id>` is the invite link. These helpers read it, change it without reloading the page, and keep who this
 * device is inside each room (so a reload does not add the same guest twice).
 */
const CHANGED = 'aangan:route-changed'

const read = (): string | null => {
  const id = new URLSearchParams(location.search).get('room')
  return id && id.trim() ? id.trim() : null
}

function subscribe(onChange: () => void) {
  window.addEventListener('popstate', onChange)
  window.addEventListener(CHANGED, onChange)
  return () => {
    window.removeEventListener('popstate', onChange)
    window.removeEventListener(CHANGED, onChange)
  }
}

/** The room id in the address, or null on the normal tabs. */
export const useRoomId = (): string | null => useSyncExternalStore(subscribe, read, () => null)

export function openRoom(id: string) {
  const url = new URL(location.href)
  url.searchParams.set('room', id)
  history.pushState(null, '', url)
  window.dispatchEvent(new Event(CHANGED))
}

/** Back to the normal app (Home). The room stays one step back in history. */
export function leaveRoomRoute() {
  const url = new URL(location.href)
  url.searchParams.delete('room')
  url.searchParams.set('tab', 'home')
  history.pushState(null, '', url)
  window.dispatchEvent(new Event(CHANGED))
}

/** The link to share. The dev-only `mock` flag is kept so an invite works on the same mock server. */
export function inviteUrl(id: string): string {
  const url = new URL(location.href)
  const keep = url.searchParams.get('mock') === '1' && import.meta.env.DEV
  url.search = ''
  url.hash = ''
  url.searchParams.set('room', id)
  if (keep) url.searchParams.set('mock', '1')
  return url.toString()
}

/* ---- who this device is in a room (localStorage, guarded: storage can be blocked) ---- */

export interface RoomIdentity {
  participant_id: string
  guest_name?: string
}

const key = (roomId: string) => `aangan.room.${roomId}`
const memory = new Map<string, string>()

export function loadIdentity(roomId: string): RoomIdentity | null {
  let raw: string | null
  try {
    raw = localStorage.getItem(key(roomId))
  } catch {
    raw = memory.get(key(roomId)) ?? null
  }
  if (!raw) return null
  try {
    const v = JSON.parse(raw) as RoomIdentity
    return typeof v.participant_id === 'string' ? v : null
  } catch {
    return null
  }
}

export function saveIdentity(roomId: string, identity: RoomIdentity | null) {
  try {
    if (identity) localStorage.setItem(key(roomId), JSON.stringify(identity))
    else localStorage.removeItem(key(roomId))
  } catch {
    if (identity) memory.set(key(roomId), JSON.stringify(identity))
    else memory.delete(key(roomId))
  }
}
