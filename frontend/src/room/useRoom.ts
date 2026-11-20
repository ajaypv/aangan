import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '@/api'
import type { Room, RoomMessage, RoomUnchanged } from '@/types'
import { normalizeRoom } from './normalize'

const POLL_MS = 1200
const HEARTBEAT_MS = 8000
/** After this many failed polls in a row the screen says it is reconnecting (one blip is not worth a banner). */
const FAILS_BEFORE_BANNER = 2

const isUnchanged = (r: Room | RoomUnchanged): r is RoomUnchanged => 'unchanged' in r && r.unchanged === true

export interface PendingMessage extends RoomMessage {
  pending: true
}

/**
 * The live room. Polls GET /rooms/{id}?since=version about every 1.2 s while the tab is visible (and straight away when it becomes
 * visible again), keeps a heartbeat going every 8 s, and shows your own message the moment you send it. Errors never throw to the screen:
 * `reconnecting` turns on after a couple of failed polls and off at the next good one.
 */
export function useRoom(roomId: string, participantId: string, initial: Room) {
  const [room, setRoom] = useState<Room>(() => normalizeRoom(initial))
  const [reconnecting, setReconnecting] = useState(false)
  const [optimistic, setOptimistic] = useState<PendingMessage[]>([])
  const version = useRef(initial.version)
  const seq = useRef(-1)

  /** Only ever move forward: a slow older response must not undo a newer one. */
  const accept = useCallback((next: Room) => {
    if (next.version < version.current) return
    version.current = next.version
    setRoom(normalizeRoom(next))
  }, [])

  useEffect(() => {
    let stopped = false
    let timer: number | undefined
    let fails = 0

    const poll = async () => {
      window.clearTimeout(timer)
      if (stopped) return
      if (document.visibilityState === 'visible') {
        try {
          const res = await api.room.get(roomId, version.current)
          if (stopped) return
          if (!isUnchanged(res)) accept(res)
          fails = 0
          setReconnecting(false)
        } catch {
          fails += 1
          if (!stopped && fails >= FAILS_BEFORE_BANNER) setReconnecting(true)
        }
      }
      if (!stopped) timer = window.setTimeout(poll, POLL_MS)
    }

    const onVisible = () => {
      if (document.visibilityState === 'visible') void poll()
    }
    document.addEventListener('visibilitychange', onVisible)
    timer = window.setTimeout(poll, POLL_MS)
    return () => {
      stopped = true
      window.clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [roomId, accept])

  useEffect(() => {
    const beat = () => {
      if (document.visibilityState === 'visible') api.room.heartbeat(roomId, participantId).catch(() => {})
    }
    beat()
    const id = window.setInterval(beat, HEARTBEAT_MS)
    return () => window.clearInterval(id)
  }, [roomId, participantId])

  const me = room.participants.find((p) => p.id === participantId)

  /** Sends a message. Resolves true when it went through; false (after dropping the preview) when it did not. */
  const send = useCallback(
    async (text: string, ask = false): Promise<boolean> => {
      const clean = text.trim()
      if (!clean) return false
      const id = seq.current--
      const ts = new Date().toTimeString().slice(0, 5)
      setOptimistic((o) => [...o, { id, kind: 'user', participant_id: participantId, name: me?.name ?? '', text: clean, ts, lang: 'en', pending: true }])
      try {
        accept(await api.room.message(roomId, participantId, clean, ask))
        return true
      } catch {
        return false
      } finally {
        setOptimistic((o) => o.filter((m) => m.id !== id))
      }
    },
    [roomId, participantId, me?.name, accept],
  )

  const approve = useCallback(
    async (yes: boolean): Promise<string | null> => {
      try {
        accept(await api.room.approve(roomId, participantId, yes))
        return null
      } catch (e) {
        return e instanceof Error ? e.message : 'That did not go through'
      }
    },
    [roomId, participantId, accept],
  )

  /** Apply a room state the screen got elsewhere (for example from the agent start call). */
  const refresh = useCallback(async () => {
    try {
      const res = await api.room.get(roomId)
      if (!isUnchanged(res)) accept(res)
    } catch {
      // The next poll will try again.
    }
  }, [roomId, accept])

  const messages = useMemo<(RoomMessage | PendingMessage)[]>(() => [...room.messages, ...optimistic], [room.messages, optimistic])

  return { room, me, messages, reconnecting, send, approve, refresh }
}
