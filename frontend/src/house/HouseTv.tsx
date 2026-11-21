import { useState } from 'react'
import { Power, Tv } from 'lucide-react'
import { api } from '@/api'
import type { HouseState } from './types'
import { youtubeEmbedUrl } from './youtube'

export function TvScreen({ tv }: { tv: HouseState['tv'] | undefined }) {
  if (!tv?.on) return <div className="house-tv-off"><Tv size={60} aria-hidden="true" /><span>TV off</span></div>
  let src: string
  try {
    src = youtubeEmbedUrl(tv.video_id)
  } catch (e) {
    return <p className="house-tv-off" role="alert">{e instanceof Error ? e.message : 'Unable to load this video.'}</p>
  }
  return <iframe key={tv.video_id} title="Living room YouTube TV" src={src} width="640" height="360"
    allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
    referrerPolicy="strict-origin-when-cross-origin" />
}

export function HouseTv({ house, onUpdate, onWatch, unavailable }: {
  house: HouseState
  onUpdate: (house: HouseState) => void
  onWatch: () => void
  unavailable: boolean
}) {
  const [video, setVideo] = useState('')
  const [working, setWorking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const tv = house.tv
  const change = async (on: boolean, videoUrl?: string) => {
    setWorking(true)
    setError(null)
    try {
      const result = await api.tool('smart_home', 'control_tv', { on, ...(videoUrl ? { video_url: videoUrl } : {}) })
      if (result.status !== 'ok') throw new Error(typeof result.result.error === 'string' ? result.result.error : 'Could not change the TV.')
      const next = result.state.domains.smart_home
      if (!next?.tv) throw new Error('The server did not return the updated TV state.')
      onUpdate(next)
      if (on) onWatch()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not change the TV. Try again.')
    } finally {
      setWorking(false)
    }
  }
  if (!tv) return <div className="house-tv-controls"><span className="house-tv-error" role="alert">Restart the Aangan backend to enable the new TV controls.</span></div>
  return (
    <div className="house-tv-controls">
      <span className="house-tv-label"><Tv size={16} aria-hidden="true" />Living room TV <strong>{tv.on ? 'On' : 'Off'}</strong></span>
      <button type="button" disabled={working || unavailable || !house.linked} aria-label={tv.on ? 'Turn TV off' : 'Turn TV on'} onClick={() => void change(!tv.on)}>
        <Power size={15} aria-hidden="true" />{working ? 'Updating...' : tv.on ? 'Turn off' : 'Turn on'}
      </button>
      <button type="button" onClick={onWatch}>Watch TV</button>
      <details>
        <summary>YouTube video</summary>
        <form onSubmit={(e) => { e.preventDefault(); void change(true, video.trim()) }}>
          <label htmlFor="house-youtube">YouTube link or video ID</label>
          <input id="house-youtube" required value={video} onChange={(e) => setVideo(e.target.value)} placeholder="https://www.youtube.com/watch?v=..." disabled={working} />
          <button type="submit" disabled={working || unavailable || !house.linked || !video.trim()}>Play on TV</button>
          <p>Starts muted. Use the YouTube controls to play, unmute or enter fullscreen. Some videos do not allow embedding.</p>
        </form>
      </details>
      {!house.linked && <span className="house-tv-hint">Link the house in Settings to use the TV.</span>}
      {tv.on && <span className="house-tv-hint">Muted by default. Tap the player to play or unmute. If this browser cannot play it, <a href={`https://www.youtube.com/watch?v=${encodeURIComponent(tv.video_id)}`} target="_blank" rel="noopener noreferrer">open on YouTube</a>.</span>}
      {error && <span className="house-tv-error" role="alert">{error}</span>}
    </div>
  )
}
