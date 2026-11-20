import type { ICameraVideoTrack, IRemoteVideoTrack } from 'agora-rtc-sdk-ng'
import { Mic, MicOff, Sparkles, Video, VideoOff, Volume2 } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { Orb } from '@/components/ask/Orb'
import { cn } from '@/lib/utils'
import type { Participant, Room } from '@/types'
import { Avatar, Button, IconButton } from '@/ui/primitives'
import { avatarOf } from './format'
import type { useRoomRtc } from './useRoomRtc'

type Rtc = ReturnType<typeof useRoomRtc>

/** Plays a camera track inside its tile and stops when the tile goes. */
function VideoSurface({ track, mirror }: { track: ICameraVideoTrack | IRemoteVideoTrack; mirror?: boolean }) {
  const el = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const node = el.current
    if (!node) return
    track.play(node, { fit: 'cover', ...(mirror === undefined ? {} : { mirror }) })
    return () => track.stop()
  }, [track, mirror])
  return <div ref={el} className="absolute inset-0 [&_video]:!object-cover" />
}

const TILE = 'relative h-[88px] w-[116px] shrink-0 snap-start overflow-hidden rounded-lg border border-line bg-surface-2 lg:h-24 lg:w-32'

function Tile({
  name,
  speaking,
  micOn,
  video,
  mirror,
  children,
}: {
  name: string
  speaking: boolean
  micOn: boolean | null
  video?: ICameraVideoTrack | IRemoteVideoTrack | null
  mirror?: boolean
  children?: React.ReactNode
}) {
  return (
    <li className={cn(TILE, speaking && 'ring-2 ring-brand ring-offset-1 ring-offset-bg')} aria-label={`${name}${speaking ? ', speaking' : ''}${video ? ', camera on' : ''}`}>
      {video ? (
        <VideoSurface track={video} mirror={mirror} />
      ) : (
        <div className="absolute inset-0 grid place-items-center pb-4" aria-hidden="true">
          {children}
        </div>
      )}
      <span className="absolute inset-x-1 bottom-1 flex items-center gap-1 rounded bg-surface/90 px-1.5 py-0.5 text-xs font-semibold" aria-hidden="true">
        <span className="min-w-0 flex-1 truncate">{name}</span>
        {micOn === false && <MicOff className="size-3.5 shrink-0 text-ink-2" />}
        {micOn === true && <Mic className="size-3.5 shrink-0 text-[var(--rw-text-success)]" />}
      </span>
    </li>
  )
}

/**
 * The people in the room, as tiles: you first, then everyone else who is here, then Aangan (the voice orb) once summoned. Everyone's
 * microphone and camera are OFF until they tap. A name comes from the participant list by the person's rtc_uid.
 */
export function VideoStrip({ room, me, rtc, agentUid, agentLive }: { room: Room; me: Participant | undefined; rtc: Rtc; agentUid: string; agentLive: boolean }) {
  const others = room.participants.filter((p) => p.id !== me?.id && p.online)
  const remoteBy = new Map(rtc.remote.map((r) => [r.uid, r]))
  const speaking = new Set(rtc.speaking)
  const agent = remoteBy.get(agentUid)

  return (
    <div className="border-b border-line bg-bg px-3 py-2.5" aria-label="Video and voice">
      <div className="flex items-center gap-2">
        <ul className="-mx-1 flex min-w-0 flex-1 snap-x gap-2 overflow-x-auto px-1 pb-0.5" aria-label="People in the call">
          {me && (
            <Tile name={`${me.name} (you)`} speaking={speaking.has(String(me.rtc_uid))} micOn={rtc.micOn} video={rtc.localVideo}>
              <Avatar member={avatarOf(me)} size={40} />
            </Tile>
          )}
          {others.map((p) => {
            const r = remoteBy.get(String(p.rtc_uid))
            return (
              <Tile key={p.id} name={p.name} speaking={speaking.has(String(p.rtc_uid))} micOn={r ? r.hasAudio : null} video={r?.hasVideo ? r.video : null}>
                <Avatar member={avatarOf(p)} size={40} presence="online" />
              </Tile>
            )
          })}
          {agentLive && (
            <Tile name="Aangan" speaking={speaking.has(agentUid)} micOn={agent ? true : null}>
              <Orb state={speaking.has(agentUid) ? 'speaking' : agent ? 'listening' : 'connecting'} size={56}>
                <Sparkles className="size-4" />
              </Orb>
            </Tile>
          )}
        </ul>
        <div className="flex shrink-0 flex-col gap-1.5 sm:flex-row" role="group" aria-label="Your microphone and camera">
          <IconButton
            label={rtc.micOn ? 'Turn off microphone' : 'Turn on microphone'}
            variant={rtc.micOn ? 'primary' : 'secondary'}
            aria-pressed={rtc.micOn}
            onClick={() => void rtc.toggleMic()}
          >
            {rtc.micOn ? <Mic className="size-5" aria-hidden="true" /> : <MicOff className="size-5" aria-hidden="true" />}
          </IconButton>
          <IconButton
            label={rtc.camOn ? 'Turn off camera' : 'Turn on camera'}
            variant={rtc.camOn ? 'primary' : 'secondary'}
            aria-pressed={rtc.camOn}
            onClick={() => void rtc.toggleCam()}
          >
            {rtc.camOn ? <Video className="size-5" aria-hidden="true" /> : <VideoOff className="size-5" aria-hidden="true" />}
          </IconButton>
        </div>
      </div>
      {rtc.audioBlocked && (
        <div className="mt-2">
          <Button size="sm" variant="secondary" icon={<Volume2 className="size-4" aria-hidden="true" />} onClick={rtc.resumeAudio}>
            Tap to hear everyone
          </Button>
        </div>
      )}
      {rtc.problem && (
        <p role="status" className="t-secondary mt-2 text-[var(--rw-text-warning)]">
          {rtc.problem}
        </p>
      )}
    </div>
  )
}
