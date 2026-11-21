import { useEffect, useState } from 'react'
import { ArrowUpRight, DoorOpen, House, Lightbulb, Settings2 } from 'lucide-react'
import { api } from '@/api'
import { HouseScene } from './HouseScene'
import { HouseTv } from './HouseTv'
import { HOUSE_DOORS, HOUSE_ROOMS, type HouseView, type HouseState } from './types'
import './house.css'

export function HousePage() {
  const [house, setHouse] = useState<HouseState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [focus, setFocus] = useState<HouseView>('all')
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    document.title = 'Cozy home · Aangan'
    let disposed = false
    let timer = 0
    let controller: AbortController | null = null
    async function refresh() {
      controller = new AbortController()
      const timeout = window.setTimeout(() => controller?.abort(), 5000)
      try {
        const next = await api.house.get(controller.signal)
        if (!disposed) {
          setHouse(next)
          setError(null)
        }
      } catch (e) {
        if (!disposed) setError(e instanceof Error ? e.message : 'Could not sync the house.')
      } finally {
        window.clearTimeout(timeout)
        if (!disposed) timer = window.setTimeout(() => void refresh(), 1000)
      }
    }
    void refresh()
    return () => {
      disposed = true
      controller?.abort()
      window.clearTimeout(timer)
      document.title = 'Aangan'
    }
  }, [retry])
  const lit = house ? HOUSE_ROOMS.filter((key) => house.lights[key].on).length : 0
  return (
    <main className="house-page">
      <HouseScene house={house} focus={focus} onReset={() => setFocus('all')} />
      <header className="house-header">
        <a className="house-brand" href="?tab=ask" aria-label="Back to Ask Aangan"><House size={21} aria-hidden="true" /><span>AANGAN<span className="house-eyebrow">a little home, connected</span></span></a>
        <a className="house-link" href="?tab=settings"><Settings2 size={16} aria-hidden="true" /><span>Settings</span></a>
      </header>
      <section className="house-intro" aria-label="House connection">
        <div className="house-eyebrow">YOUR VIRTUAL HOUSE</div>
        <h1>Cozy home.</h1>
        <p>A word from you.<br />A little change at home.</p>
        <span className={`house-connection ${house?.linked && !error ? 'is-live' : ''}`} role="status">
          <span aria-hidden="true" />{error ? 'Sync unavailable' : house?.linked ? 'Linked to Aangan' : house ? 'Not linked yet' : 'Connecting...'}
        </span>
      </section>
      {error && <div className="house-sync-error" role="alert">
        <span>{error} {house ? 'Showing the last confirmed state.' : ''}</span>
        <button type="button" onClick={() => setRetry((n) => n + 1)}>Retry connection</button>
      </div>}
      <footer className="house-footer">
        {house && <HouseTv house={house} unavailable={error !== null} onWatch={() => setFocus('tv')} onUpdate={(next) => {
          setHouse(next)
          setRetry((n) => n + 1)
        }} />}
        {house && <nav className="house-rooms" aria-label="Focus a room">
          <button type="button" aria-pressed={focus === 'all'} onClick={() => setFocus('all')}>
            <House size={17} aria-hidden="true" /><span>Whole house<small>{lit} of 4 lights on</small></span>
          </button>
          {HOUSE_ROOMS.map((key) => {
            const light = house.lights[key]
            return <button type="button" key={key} className={light.on ? 'light-on' : ''} aria-pressed={focus === key} onClick={() => setFocus(key)}>
              <Lightbulb size={17} aria-hidden="true" /><span>{light.name}<small>{light.on ? `${light.brightness}% brightness` : 'Light off'}</small></span>
            </button>
          })}
        </nav>}
        <div className="house-bottom">
          <div className="house-current">
            <p className="house-action" role="status">{house?.last_action ?? 'Drag to explore. Scroll or pinch to zoom.'}</p>
            {house && <div className="house-doors" aria-label="Door states">{HOUSE_DOORS.map((key) => <span key={key}><DoorOpen size={13} aria-hidden="true" />{house.doors[key].name}: {house.doors[key].open ? 'open' : 'closed'}</span>)}</div>}
          </div>
          <a className="house-ask" href={house?.linked ? '?tab=ask' : '?tab=settings'} target="_blank" rel="noopener noreferrer">
            {house?.linked ? 'Ask Aangan to change it' : 'Link house in Settings'}<ArrowUpRight size={17} aria-hidden="true" />
          </a>
        </div>
        <div className="house-fineprint"><span>Virtual devices only · Drag to orbit · Scroll to zoom</span><a href="https://3dassets.dev/packs/cozy-home-interiors" target="_blank" rel="noopener noreferrer">3D Assets · CC0</a></div>
      </footer>
    </main>
  )
}
