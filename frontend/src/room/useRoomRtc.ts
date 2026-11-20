import { useCallback, useEffect, useRef, useState } from 'react'
import type { IAgoraRTCClient, ICameraVideoTrack, IMicrophoneAudioTrack, IRemoteAudioTrack, IRemoteVideoTrack } from 'agora-rtc-sdk-ng'
import { api } from '@/api'

/*
 * Video and audio for a room, on Agora's Web SDK with the token from POST /rooms/{id}/rtc.
 * - Joins the room's channel when the screen opens, but publishes nothing: the microphone and the camera are OFF until tapped.
 * - Video is capped at 360p (profile 360p_7); Agora bills video by combined pixels.
 * - Remote audio plays after a tap: if the browser blocks autoplay, `audioBlocked` turns on and the next tap anywhere resumes it.
 * - Everything is closed on leave. In the dev mock (app_id "mock") nothing joins, but the local camera and microphone still work.
 */

export interface RemoteMedia {
  uid: string
  audio: IRemoteAudioTrack | null
  video: IRemoteVideoTrack | null
  hasAudio: boolean
  hasVideo: boolean
}

export type RtcStatus = 'idle' | 'connecting' | 'connected' | 'error'

type AgoraModule = typeof import('agora-rtc-sdk-ng').default

const errName = (e: unknown): string => (e instanceof Error || e instanceof DOMException ? e.name : '')

function mediaProblem(e: unknown, what: 'camera' | 'microphone'): string {
  const n = errName(e)
  if (!window.isSecureContext || n === 'InsecureContext') return `The ${what} needs a secure page (https or localhost).`
  if (n === 'NotAllowedError' || n === 'PermissionDeniedError' || (e as { code?: string })?.code === 'PERMISSION_DENIED')
    return `The ${what} is blocked. Allow it in your browser's site settings, then tap again.`
  if (n === 'NotFoundError' || n === 'DevicesNotFoundError' || (e as { code?: string })?.code === 'DEVICE_NOT_FOUND') return `No ${what} was found on this device.`
  if (n === 'NotReadableError') return `Another app is using the ${what}.`
  return `Could not start the ${what}.`
}

export function useRoomRtc(roomId: string, participantId: string, enabled = true) {
  const [status, setStatus] = useState<RtcStatus>('idle')
  const [localUid, setLocalUid] = useState<string | null>(null)
  const [micOn, setMicOn] = useState(false)
  const [camOn, setCamOn] = useState(false)
  const [localVideo, setLocalVideo] = useState<ICameraVideoTrack | null>(null)
  const [remote, setRemote] = useState<RemoteMedia[]>([])
  const [speaking, setSpeaking] = useState<string[]>([])
  const [audioBlocked, setAudioBlocked] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)

  const agora = useRef<AgoraModule | null>(null)
  const client = useRef<IAgoraRTCClient | null>(null)
  const joined = useRef(false)
  const mic = useRef<IMicrophoneAudioTrack | null>(null)
  const cam = useRef<ICameraVideoTrack | null>(null)
  const busy = useRef({ mic: false, cam: false })
  const uid = useRef<string | null>(null)
  const gen = useRef(0)

  const syncRemote = useCallback(() => {
    const c = client.current
    if (!c) return
    setRemote(
      c.remoteUsers.map((u) => ({
        uid: String(u.uid),
        audio: u.audioTrack ?? null,
        video: u.videoTrack ?? null,
        hasAudio: u.hasAudio,
        hasVideo: u.hasVideo,
      })),
    )
  }, [])

  useEffect(() => {
    if (!enabled) return
    const g = ++gen.current
    const alive = () => g === gen.current
    setStatus('connecting')
    setProblem(null)

    void (async () => {
      try {
        const AgoraRTC = (await import('agora-rtc-sdk-ng')).default
        if (!alive()) return
        agora.current = AgoraRTC
        AgoraRTC.setLogLevel?.(3)
        ;(AgoraRTC as unknown as { onAudioAutoplayFailed?: () => void }).onAudioAutoplayFailed = () => {
          if (alive()) setAudioBlocked(true)
        }
        const session = await api.room.rtc(roomId, participantId)
        if (!alive()) return
        uid.current = String(session.uid)
        setLocalUid(String(session.uid))

        if (import.meta.env.DEV && session.app_id === 'mock') {
          setStatus('connected')
          return
        }

        const c = AgoraRTC.createClient({ mode: 'rtc', codec: 'vp8' })
        client.current = c
        c.on('user-published', async (user, mediaType) => {
          try {
            await c.subscribe(user, mediaType)
            if (mediaType === 'audio') user.audioTrack?.play()
          } catch {
            // A failed subscribe is retried by the SDK on the next publish event.
          }
          if (alive()) syncRemote()
        })
        c.on('user-unpublished', () => alive() && syncRemote())
        c.on('user-joined', () => alive() && syncRemote())
        c.on('user-left', () => alive() && syncRemote())
        c.on('connection-state-change', (cur) => {
          if (!alive()) return
          setStatus(cur === 'CONNECTED' ? 'connected' : cur === 'DISCONNECTED' ? 'error' : 'connecting')
        })
        c.enableAudioVolumeIndicator()
        let last = ''
        c.on('volume-indicator', (vols) => {
          if (!alive()) return
          const ids = vols
            .filter((v) => v.level >= 8)
            .map((v) => (v.uid === 0 ? (uid.current ?? '') : String(v.uid)))
            .sort()
          const key = ids.join(',')
          if (key !== last) {
            last = key
            setSpeaking(ids)
          }
        })

        await c.join(session.app_id, session.channel, session.token, session.uid)
        if (!alive()) {
          void c.leave().catch(() => {})
          return
        }
        joined.current = true
        setStatus('connected')
        syncRemote()
        // Someone who turned a camera or mic on before the user opened the tab is already in remoteUsers: subscribe to them too.
        for (const u of c.remoteUsers) {
          for (const kind of ['audio', 'video'] as const) {
            if ((kind === 'audio' ? u.hasAudio : u.hasVideo) && !(kind === 'audio' ? u.audioTrack : u.videoTrack)) {
              try {
                await c.subscribe(u, kind)
                if (kind === 'audio') u.audioTrack?.play()
              } catch {
                // Ignored: the next publish event retries.
              }
            }
          }
        }
        if (alive()) syncRemote()
      } catch {
        if (alive()) {
          setStatus('error')
          setProblem('Video and voice could not connect. The plan and chat still work.')
        }
      }
    })()

    return () => {
      gen.current++
      const c = client.current
      const m = mic.current
      const v = cam.current
      client.current = null
      mic.current = null
      cam.current = null
      joined.current = false
      m?.close()
      v?.close()
      if (c) void c.leave().catch(() => {})
      setMicOn(false)
      setCamOn(false)
      setLocalVideo(null)
      setRemote([])
      setSpeaking([])
      setStatus('idle')
    }
  }, [roomId, participantId, enabled, syncRemote])

  const resumeAudio = useCallback(() => {
    for (const u of client.current?.remoteUsers ?? []) u.audioTrack?.play()
    setAudioBlocked(false)
  }, [])

  // The first tap or key press after autoplay was blocked is the gesture the browser wanted.
  useEffect(() => {
    if (!audioBlocked) return
    const go = () => resumeAudio()
    window.addEventListener('pointerdown', go, { once: true })
    window.addEventListener('keydown', go, { once: true })
    return () => {
      window.removeEventListener('pointerdown', go)
      window.removeEventListener('keydown', go)
    }
  }, [audioBlocked, resumeAudio])

  const toggleMic = useCallback(async (): Promise<boolean> => {
    if (busy.current.mic) return micOn
    busy.current.mic = true
    setProblem(null)
    try {
      if (mic.current) {
        const t = mic.current
        mic.current = null
        if (joined.current && client.current) await client.current.unpublish(t).catch(() => {})
        t.close()
        setMicOn(false)
        return false
      }
      const AgoraRTC = agora.current ?? (await import('agora-rtc-sdk-ng')).default
      if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) throw Object.assign(new Error('Insecure page'), { name: 'InsecureContext' })
      const t = await AgoraRTC.createMicrophoneAudioTrack({ AEC: true, ANS: true, AGC: true })
      if (joined.current && client.current) await client.current.publish([t])
      mic.current = t
      setMicOn(true)
      return true
    } catch (e) {
      setProblem(mediaProblem(e, 'microphone'))
      return false
    } finally {
      busy.current.mic = false
    }
  }, [micOn])

  const toggleCam = useCallback(async (): Promise<boolean> => {
    if (busy.current.cam) return camOn
    busy.current.cam = true
    setProblem(null)
    try {
      if (cam.current) {
        const t = cam.current
        cam.current = null
        setLocalVideo(null)
        if (joined.current && client.current) await client.current.unpublish(t).catch(() => {})
        t.close()
        setCamOn(false)
        return false
      }
      const AgoraRTC = agora.current ?? (await import('agora-rtc-sdk-ng')).default
      if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) throw Object.assign(new Error('Insecure page'), { name: 'InsecureContext' })
      const t = await AgoraRTC.createCameraVideoTrack({ encoderConfig: '360p_7' })
      if (joined.current && client.current) await client.current.publish([t])
      cam.current = t
      setLocalVideo(t)
      setCamOn(true)
      return true
    } catch (e) {
      setProblem(mediaProblem(e, 'camera'))
      return false
    } finally {
      busy.current.cam = false
    }
  }, [camOn])

  return { status, localUid, micOn, camOn, localVideo, remote, speaking, audioBlocked, problem, toggleMic, toggleCam, resumeAudio }
}
